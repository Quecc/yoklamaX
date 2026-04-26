"""
AI Destekli Yoklama Sistemi — Flask Ana Uygulama
Yüz tanıma ile otomatik yoklama alan web tabanlı platform.
"""

import os
import json
import base64
import numpy as np
import cv2
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from face_manager import FaceManager
from pdf_generator import generate_pdf

# Flask uygulaması
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Yüz tanıma yöneticisi
face_manager = FaceManager(faces_dir="faces/")

# Yoklama durumu (bellekte tutuluyor)
attendance_state = {
    "date": datetime.now().strftime('%Y-%m-%d'),
    "started_at": None,
    "students": {}  # id -> {name, status, time, auto}
}


def init_attendance():
    """Yoklama durumunu kayıtlı öğrencilerle başlat."""
    global attendance_state
    attendance_state["date"] = datetime.now().strftime('%Y-%m-%d')
    attendance_state["started_at"] = datetime.now().strftime('%H:%M:%S')
    attendance_state["students"] = {}

    for student in face_manager.get_all_students():
        sid = student["id"]
        attendance_state["students"][sid] = {
            "id": sid,
            "name": student["name"],
            "status": "absent",
            "time": None,
            "auto": False  # otomatik mi yoksa manuel mi işaretlendi
        }


# ─── ROUTES ─────────────────────────────────────────

@app.route('/')
def index():
    """Ana sayfa."""
    return render_template('index.html')


@app.route('/api/recognize', methods=['POST'])
def recognize():
    """
    Kamera frame'ini alır, yüz tanıma yapar, yoklamayı günceller.
    Body: { "image": "data:image/jpeg;base64,..." }
    """
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({"error": "Görüntü verisi eksik"}), 400

        # Base64 decode
        image_data = data['image']
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"error": "Görüntü decode edilemedi"}), 400

        # Performans için küçült
        scale = 0.5
        small_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)

        # Yüz tanıma (DeepFace BGR bekler)
        faces = face_manager.recognize(small_frame, tolerance=0.35)

        # Koordinatları orijinal boyuta ölçekle
        scale_inv = int(1 / scale)
        for face in faces:
            face['box']['top'] *= scale_inv
            face['box']['right'] *= scale_inv
            face['box']['bottom'] *= scale_inv
            face['box']['left'] *= scale_inv

        # Yoklamayı güncelle
        newly_marked = []
        for face in faces:
            if face['matched'] and face['id']:
                sid = face['id']
                if sid in attendance_state['students']:
                    student = attendance_state['students'][sid]
                    if student['status'] == 'absent':
                        student['status'] = 'present'
                        student['time'] = datetime.now().strftime('%H:%M:%S')
                        student['auto'] = True
                        newly_marked.append(student['name'])

        return jsonify({
            "faces": faces,
            "newly_marked": newly_marked,
            "attendance": get_attendance_list()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    """Mevcut yoklama listesini döner."""
    return jsonify({
        "date": attendance_state["date"],
        "started_at": attendance_state["started_at"],
        "students": get_attendance_list(),
        "stats": get_attendance_stats()
    })


@app.route('/api/attendance/toggle', methods=['POST'])
def toggle_attendance():
    """Manuel yoklama değişikliği."""
    data = request.get_json()
    sid = data.get('id')

    if sid and sid in attendance_state['students']:
        student = attendance_state['students'][sid]
        if student['status'] == 'present':
            student['status'] = 'absent'
            student['time'] = None
            student['auto'] = False
        else:
            student['status'] = 'present'
            student['time'] = datetime.now().strftime('%H:%M:%S')
            student['auto'] = False

        return jsonify({"success": True, "student": student})

    return jsonify({"error": "Öğrenci bulunamadı"}), 404


@app.route('/api/attendance/reset', methods=['POST'])
def reset_attendance():
    """Yoklamayı sıfırla."""
    init_attendance()
    return jsonify({"success": True, "message": "Yoklama sıfırlandı"})


@app.route('/api/attendance/save', methods=['POST'])
def save_attendance():
    """Yoklamayı JSON dosyasına kaydet."""
    records_dir = os.path.join(os.path.dirname(__file__), 'attendance_records')
    os.makedirs(records_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'yoklama_{timestamp}.json'
    filepath = os.path.join(records_dir, filename)

    save_data = {
        "date": attendance_state["date"],
        "saved_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "started_at": attendance_state["started_at"],
        "stats": get_attendance_stats(),
        "students": get_attendance_list()
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "success": True,
        "message": f"Yoklama kaydedildi: {filename}",
        "filename": filename
    })


@app.route('/api/attendance/pdf', methods=['GET'])
def download_pdf():
    """PDF rapor oluştur ve indir."""
    try:
        attendance_list = get_attendance_list()
        pdf_path = generate_pdf(attendance_list)
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'yoklama_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students', methods=['GET'])
def get_students():
    """Kayıtlı öğrenci listesi."""
    return jsonify({
        "students": face_manager.get_all_students(),
        "count": face_manager.get_student_count()
    })


@app.route('/api/reload-faces', methods=['POST'])
def reload_faces():
    """/faces/ klasörünü yeniden tara."""
    count = face_manager.load_faces()
    init_attendance()
    return jsonify({
        "success": True,
        "message": f"{count} yüz yüklendi",
        "count": count
    })


# ─── HELPER FUNCTIONS ──────────────────────────────

def get_attendance_list():
    """Yoklama listesini sıralı olarak döner."""
    students = list(attendance_state['students'].values())
    # Önce var olanlar, sonra yoklar; kendi içinde isme göre
    students.sort(key=lambda s: (0 if s['status'] == 'present' else 1, s['name']))
    return students


def get_attendance_stats():
    """Yoklama istatistiklerini hesaplar."""
    students = list(attendance_state['students'].values())
    total = len(students)
    present = sum(1 for s in students if s['status'] == 'present')
    absent = total - present
    rate = (present / total * 100) if total > 0 else 0
    return {
        "total": total,
        "present": present,
        "absent": absent,
        "rate": round(rate, 1)
    }


# ─── STARTUP ───────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  AI Destekli Yoklama Sistemi")
    print("=" * 50)
    print("\n[Başlatılıyor] Yüz verileri yükleniyor...\n")

    face_manager.load_faces()
    init_attendance()

    print(f"\n[Hazır] {face_manager.get_student_count()} öğrenci yüklendi")
    print("[Sunucu] http://localhost:5050 adresinde çalışıyor\n")

    app.run(debug=True, host='0.0.0.0', port=5050)
