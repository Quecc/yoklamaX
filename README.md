# 🎓 YoklamaX — AI Destekli Yoklama Sistemi

Yapay zekâ destekli yüz tanıma teknolojisi ile otomatik yoklama alan web tabanlı platform.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)
![DeepFace](https://img.shields.io/badge/DeepFace-AI-orange.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-4.13-red.svg)

---

## 📋 Proje Özeti

YoklamaX, `/faces/` klasörüne eklenen öğrenci fotoğrafları ile yüz tanıma yaparak otomatik yoklama alan bir sistemdir. Minimum kurulum ile (sadece klasöre fotoğraf ekleyerek) hızlı ve pratik yoklama alınmasını sağlar.

## 🚀 Özellikler

- **Gerçek zamanlı yüz tanıma** — Kamera üzerinden anlık yüz tespiti ve eşleştirme
- **Otomatik yoklama** — Tanınan öğrenciler otomatik olarak "var" işaretlenir
- **Duplicate engelleme** — Aynı kişi tekrar tekrar sayılmaz
- **Manuel override** — Tıklama ile yoklama durumu değiştirilebilir
- **PDF rapor** — Tek tıkla profesyonel yoklama raporu (Türkçe karakter destekli)
- **Yoklama kaydı** — JSON formatında kayıt
- **Bounding box + isim etiketi** — Kamera görüntüsünde tanınan kişilerin isimleri
- **Apple tarzı tasarım** — Beyaz, sade, lüks arayüz

## 📁 Proje Yapısı

```
yoklamaX/
├── app.py                    # Flask ana uygulama + API endpoint'leri
├── face_manager.py           # Yüz encoding yükleme ve eşleştirme (DeepFace)
├── pdf_generator.py          # PDF rapor oluşturma (ReportLab)
├── requirements.txt          # Python bağımlılıkları
├── faces/                    # Referans yüz fotoğrafları (kullanıcı ekler)
│   └── 12345_ahmet.jpg       # Format: numara_isim.jpg
├── attendance_records/       # Yoklama kayıtları (JSON)
├── pdf_reports/              # Oluşturulan PDF raporları
├── fonts/
│   └── DejaVuSans.ttf        # Türkçe karakter destekli font
├── static/
│   ├── css/
│   │   └── style.css         # Apple-inspired tasarım
│   └── js/
│       └── app.js            # Frontend: kamera, API, UI
└── templates/
    └── index.html            # Ana sayfa
```

## 🛠️ Kurulum

### 1. Gereksinimler

- Python 3.9+
- Xcode Command Line Tools (macOS)
- Web kamerası

### 2. Bağımlılıkları Kur

```bash
# macOS'ta Xcode CLI Tools gerekli
xcode-select --install

# Python paketlerini kur
pip3 install --user flask opencv-python-headless numpy reportlab Pillow deepface tf-keras
```

### 3. Öğrenci Fotoğrafları Ekle

`faces/` klasörüne öğrenci fotoğrafları ekleyin:

```
faces/
├── 12345_ahmet_yilmaz.jpg
├── 12346_elif_kaya.png
└── 12347_mehmet_demir.jpg
```

**Dosya adı formatı:** `numara_isim.jpg`
- `_` ile ayrılan ilk kısım öğrenci numarası
- Geri kalanı öğrenci adı
- Desteklenen formatlar: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`

### 4. Sunucuyu Başlat

```bash
python3 app.py
```

Tarayıcıda açın: **http://localhost:5050**

## 🔌 API Endpoint'leri

| Endpoint | Method | Açıklama |
|---|---|---|
| `/` | GET | Ana sayfa |
| `/api/recognize` | POST | Frame gönder → yüz tanıma |
| `/api/attendance` | GET | Yoklama listesi |
| `/api/attendance/toggle` | POST | Manuel yoklama değişikliği |
| `/api/attendance/reset` | POST | Yoklamayı sıfırla |
| `/api/attendance/save` | POST | Yoklamayı JSON'a kaydet |
| `/api/attendance/pdf` | GET | PDF rapor indir |
| `/api/students` | GET | Kayıtlı öğrenci listesi |
| `/api/reload-faces` | POST | Yüzleri yeniden yükle |

## 🔧 Teknik Yapı

- **Backend:** Python + Flask
- **Görüntü İşleme:** OpenCV (Haar Cascade ile yüz tespiti)
- **Yüz Tanıma:** DeepFace (Facenet modeli, cosine distance)
- **PDF:** ReportLab (Türkçe DejaVuSans font)
- **Frontend:** Vanilla HTML/CSS/JS
- **Tasarım:** Apple-inspired minimal beyaz tema

## 📊 Çalışma Mantığı

```
1. Kamera açılır → gerçek zamanlı görüntü alınır
2. Her 600ms'de frame backend'e gönderilir
3. OpenCV ile yüzler tespit edilir
4. DeepFace ile yüz embedding'i hesaplanır
5. Bilinen yüzlerle cosine distance karşılaştırması yapılır
6. Eşleşme bulunursa → öğrenci "var" işaretlenir
7. Duplicate kontrolü → aynı kişi tekrar sayılmaz
8. Bounding box + isim etiketi ekrana çizilir
```

---

## 📜 Implementation Plan

### Amaç
Minimum kurulum ile (sadece klasöre fotoğraf ekleyerek) hızlı ve pratik bir yoklama sistemi oluşturmak.

### Mimari Kararlar

1. **DeepFace tercih edildi** — `face_recognition` (dlib) C++ derleme gerektirdiği için, saf Python olan DeepFace kullanıldı
2. **Facenet modeli** — Hafif, hızlı ve doğru embedding modeli
3. **OpenCV Haar Cascade** — Hızlı yüz tespiti için (DNN modeline göre daha az kaynak)
4. **Cosine Distance** — Yüz eşleştirme metriği (tolerance: 0.35)
5. **Client-side kamera** — Kamera tarayıcıda açılır, frame'ler base64 olarak backend'e POST edilir
6. **Bellekte yoklama** — Oturum bazlı, JSON'a kaydedilebilir
7. **ReportLab + DejaVuSans** — Türkçe karakter destekli PDF çıktısı

### Akış Diyagramı

```
┌─────────────┐     base64 frame      ┌──────────────┐
│   Tarayıcı  │ ──────────────────────►│  Flask API   │
│   (Kamera)  │                        │  /recognize  │
│             │◄──────────────────────  │              │
│  Canvas +   │  faces + attendance    │  FaceManager │
│  Bounding   │                        │  .recognize()│
│  Box çiz    │                        └──────┬───────┘
└─────────────┘                               │
                                              ▼
                                     ┌────────────────┐
                                     │  /faces/ dir   │
                                     │  (embeddings)  │
                                     └────────────────┘
```

### Dosya Açıklamaları

| Dosya | Satır | Açıklama |
|---|---|---|
| `app.py` | ~263 | Flask sunucu, 8 API endpoint, yoklama state yönetimi |
| `face_manager.py` | ~200 | DeepFace ile yüz yükleme/eşleştirme, Haar Cascade tespiti |
| `pdf_generator.py` | ~170 | ReportLab PDF, zebra striping, renk kodlu durum |
| `style.css` | ~580 | Apple-inspired minimal beyaz tema, responsive |
| `app.js` | ~370 | Kamera, frame capture, bounding box çizimi, toast |
| `index.html` | ~195 | Tek sayfa: kamera paneli + yoklama listesi + toolbar |

---

*Bu proje AI destekli otomatik yoklama almak için geliştirilmiştir.*
