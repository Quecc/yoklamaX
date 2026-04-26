/**
 * AI Yoklama Sistemi — Frontend JavaScript
 * Kamera yönetimi, API iletişimi, yoklama UI güncelleme
 */

// ─── State ──────────────────────────────────────────
let cameraActive = false;
let videoStream = null;
let recognitionInterval = null;
let fpsInterval = null;
let frameCount = 0;
let lastFpsTime = Date.now();
let isProcessing = false;

const video = document.getElementById('video');
const overlayCanvas = document.getElementById('overlay-canvas');
const ctx = overlayCanvas.getContext('2d');

// ─── Initialize ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    updateDateTime();
    setInterval(updateDateTime, 1000);
    loadAttendance();
});

// ─── Date/Time ──────────────────────────────────────
function updateDateTime() {
    const now = new Date();
    const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('current-date').textContent = now.toLocaleDateString('tr-TR', dateOptions);
    document.getElementById('current-time').textContent = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ─── Camera Control ─────────────────────────────────
async function toggleCamera() {
    if (cameraActive) {
        stopCamera();
    } else {
        await startCamera();
    }
}

async function startCamera() {
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user'
            }
        });

        video.srcObject = videoStream;
        await video.play();

        // Canvas boyutlandırma
        video.addEventListener('loadedmetadata', () => {
            overlayCanvas.width = video.videoWidth;
            overlayCanvas.height = video.videoHeight;
        });

        // UI güncelle
        cameraActive = true;
        document.getElementById('camera-container').classList.add('active');
        
        const btn = document.getElementById('btn-camera');
        btn.classList.add('active');
        btn.querySelector('span').textContent = 'Kamerayı Durdur';

        updateStatus(true);
        showToast('success', 'Kamera Açıldı', 'Yüz tanıma başlatıldı');

        // Yüz tanıma döngüsü (her 600ms)
        recognitionInterval = setInterval(captureAndRecognize, 600);

        // FPS sayacı
        fpsInterval = setInterval(updateFPS, 1000);

    } catch (err) {
        console.error('Kamera hatası:', err);
        showToast('error', 'Kamera Hatası', 'Kamera erişimi sağlanamadı. Tarayıcı izinlerini kontrol edin.');
    }
}

function stopCamera() {
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }

    if (recognitionInterval) {
        clearInterval(recognitionInterval);
        recognitionInterval = null;
    }

    if (fpsInterval) {
        clearInterval(fpsInterval);
        fpsInterval = null;
    }

    video.srcObject = null;
    cameraActive = false;

    document.getElementById('camera-container').classList.remove('active');
    
    const btn = document.getElementById('btn-camera');
    btn.classList.remove('active');
    btn.querySelector('span').textContent = 'Kamerayı Başlat';

    // Overlay temizle
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    updateStatus(false);
    document.getElementById('face-count').textContent = '0';
    document.getElementById('recognized-count').textContent = '0';
    document.getElementById('fps-counter').textContent = '0';

    showToast('info', 'Kamera Kapatıldı', 'Yüz tanıma durduruldu');
}

// ─── Frame Capture & Recognition ────────────────────
async function captureAndRecognize() {
    if (!cameraActive || isProcessing) return;
    isProcessing = true;

    try {
        // Canvas'a frame çiz
        const captureCanvas = document.createElement('canvas');
        captureCanvas.width = video.videoWidth;
        captureCanvas.height = video.videoHeight;
        const captureCtx = captureCanvas.getContext('2d');
        captureCtx.drawImage(video, 0, 0);

        // Base64'e dönüştür (kaliteyi düşür performans için)
        const imageData = captureCanvas.toDataURL('image/jpeg', 0.6);

        // API'ye gönder
        const response = await fetch('/api/recognize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageData })
        });

        if (!response.ok) throw new Error('API hatası');

        const result = await response.json();
        frameCount++;

        // Yüzleri çiz
        drawFaceBoxes(result.faces || []);

        // İstatistikleri güncelle
        const faces = result.faces || [];
        document.getElementById('face-count').textContent = faces.length;
        document.getElementById('recognized-count').textContent = 
            faces.filter(f => f.matched).length;

        // Yeni tanınan öğrenciler
        if (result.newly_marked && result.newly_marked.length > 0) {
            result.newly_marked.forEach(name => {
                showToast('success', 'Öğrenci Tanındı', `${name} yoklamaya eklendi ✓`);
            });
        }

        // Yoklama listesini güncelle
        if (result.attendance) {
            updateAttendanceUI(result.attendance);
        }

    } catch (err) {
        console.error('Tanıma hatası:', err);
    } finally {
        isProcessing = false;
    }
}

// ─── Draw Face Boxes ────────────────────────────────
function drawFaceBoxes(faces) {
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    // Canvas boyutunu video ile eşle
    if (overlayCanvas.width !== video.videoWidth) {
        overlayCanvas.width = video.videoWidth;
        overlayCanvas.height = video.videoHeight;
    }

    faces.forEach(face => {
        const { top, right, bottom, left } = face.box;
        const width = right - left;
        const height = bottom - top;

        if (face.matched) {
            // Tanınan yüz - yeşil
            ctx.strokeStyle = '#00b894';
            ctx.shadowColor = '#00b894';
            ctx.shadowBlur = 15;
            ctx.lineWidth = 3;

            // İsim etiketi arka planı
            ctx.fillStyle = 'rgba(0, 184, 148, 0.85)';
            const labelText = `${face.name} (${(1 - face.distance).toFixed(0) * 100}%)`;
            ctx.font = 'bold 14px Inter, sans-serif';
            const textWidth = ctx.measureText(labelText).width;
            
            // Üst etiket
            const labelHeight = 24;
            const labelY = top - labelHeight - 4;
            ctx.beginPath();
            ctx.roundRect(left - 1, labelY, textWidth + 16, labelHeight, 4);
            ctx.fill();

            // İsim yazısı
            ctx.fillStyle = '#ffffff';
            ctx.shadowBlur = 0;
            ctx.fillText(labelText, left + 7, labelY + 17);

        } else {
            // Tanınmayan yüz - turuncu
            ctx.strokeStyle = '#fdcb6e';
            ctx.shadowColor = '#fdcb6e';
            ctx.shadowBlur = 10;
            ctx.lineWidth = 2;

            // "Bilinmeyen" etiketi
            ctx.fillStyle = 'rgba(253, 203, 110, 0.8)';
            ctx.font = 'bold 12px Inter, sans-serif';
            const labelHeight = 22;
            const labelY = top - labelHeight - 4;
            ctx.beginPath();
            ctx.roundRect(left - 1, labelY, 90, labelHeight, 4);
            ctx.fill();

            ctx.fillStyle = '#1a1a2e';
            ctx.shadowBlur = 0;
            ctx.fillText('Bilinmeyen', left + 7, labelY + 16);
        }

        // Bounding box - köşe çizgileri stili
        ctx.shadowBlur = face.matched ? 15 : 10;
        const cornerLength = Math.min(width, height) * 0.25;

        // Sol üst köşe
        ctx.beginPath();
        ctx.moveTo(left, top + cornerLength);
        ctx.lineTo(left, top);
        ctx.lineTo(left + cornerLength, top);
        ctx.stroke();

        // Sağ üst köşe
        ctx.beginPath();
        ctx.moveTo(right - cornerLength, top);
        ctx.lineTo(right, top);
        ctx.lineTo(right, top + cornerLength);
        ctx.stroke();

        // Sol alt köşe
        ctx.beginPath();
        ctx.moveTo(left, bottom - cornerLength);
        ctx.lineTo(left, bottom);
        ctx.lineTo(left + cornerLength, bottom);
        ctx.stroke();

        // Sağ alt köşe
        ctx.beginPath();
        ctx.moveTo(right - cornerLength, bottom);
        ctx.lineTo(right, bottom);
        ctx.lineTo(right, bottom - cornerLength);
        ctx.stroke();

        ctx.shadowBlur = 0;
    });
}

// ─── Attendance UI ──────────────────────────────────
async function loadAttendance() {
    try {
        const response = await fetch('/api/attendance');
        const data = await response.json();
        updateAttendanceUI(data.students || []);
        updateStats(data.stats);
    } catch (err) {
        console.error('Yoklama yükleme hatası:', err);
    }
}

function updateAttendanceUI(students) {
    const list = document.getElementById('student-list');
    const emptyState = document.getElementById('empty-state');

    if (!students || students.length === 0) {
        list.innerHTML = '';
        list.appendChild(createEmptyState());
        updateStats({ total: 0, present: 0, absent: 0, rate: 0 });
        return;
    }

    // Mevcut kartları takip et
    const existingCards = {};
    list.querySelectorAll('.student-card').forEach(card => {
        existingCards[card.dataset.id] = card;
    });

    // Boş durumu kaldır
    const empty = list.querySelector('.empty-state');
    if (empty) empty.remove();

    // Öğrenci kartlarını güncelle
    const fragment = document.createDocumentFragment();
    students.forEach((student, index) => {
        const card = createStudentCard(student, index);
        
        // Yeni eklenen öğrenci animasyonu
        if (existingCards[student.id]) {
            const oldCard = existingCards[student.id];
            const wasAbsent = oldCard.classList.contains('absent');
            const nowPresent = student.status === 'present';
            
            if (wasAbsent && nowPresent) {
                card.classList.add('newly-added');
            }
        }
        
        fragment.appendChild(card);
    });

    list.innerHTML = '';
    list.appendChild(fragment);

    // İstatistikleri güncelle
    const total = students.length;
    const present = students.filter(s => s.status === 'present').length;
    const absent = total - present;
    const rate = total > 0 ? ((present / total) * 100).toFixed(1) : 0;
    updateStats({ total, present, absent, rate });
}

function createStudentCard(student, index) {
    const card = document.createElement('div');
    card.className = `student-card ${student.status}`;
    card.dataset.id = student.id;
    card.style.animationDelay = `${index * 0.03}s`;
    card.onclick = () => toggleStudentStatus(student.id);

    const initials = student.name.split(' ').map(n => n[0]).join('').substring(0, 2);
    const statusIcon = student.status === 'present' ? '✓' : '✗';
    const timeText = student.time || '';

    card.innerHTML = `
        <div class="student-avatar">${initials}</div>
        <div class="student-info">
            <div class="student-name">${student.name}</div>
            <div class="student-id">#${student.id}</div>
        </div>
        <div class="student-status">
            <div class="status-icon">${statusIcon}</div>
            ${timeText ? `<span class="status-time">${timeText}</span>` : ''}
        </div>
    `;

    return card;
}

function createEmptyState() {
    const div = document.createElement('div');
    div.className = 'empty-state';
    div.id = 'empty-state';
    div.innerHTML = `
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
        <p>Öğrenci verisi yüklenmedi</p>
        <span>/faces/ klasörüne fotoğraf ekleyin ve "Yüzleri Yenile" butonuna tıklayın</span>
    `;
    return div;
}

function updateStats(stats) {
    document.getElementById('badge-total').textContent = stats.total || 0;
    document.getElementById('badge-present').textContent = stats.present || 0;
    document.getElementById('badge-absent').textContent = stats.absent || 0;

    const rate = stats.rate || 0;
    document.getElementById('progress-fill').style.width = `${rate}%`;
    document.getElementById('progress-text').textContent = `%${rate} Katılım`;
}

// ─── Student Toggle ─────────────────────────────────
async function toggleStudentStatus(studentId) {
    try {
        const response = await fetch('/api/attendance/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: studentId })
        });

        const data = await response.json();
        if (data.success) {
            loadAttendance();
            const status = data.student.status === 'present' ? 'var' : 'yok';
            showToast('info', 'Manuel Güncelleme', `${data.student.name}: ${status}`);
        }
    } catch (err) {
        showToast('error', 'Hata', 'Durum güncellenemedi');
    }
}

// ─── Search/Filter ──────────────────────────────────
function filterStudents() {
    const query = document.getElementById('search-input').value.toLowerCase();
    const cards = document.querySelectorAll('.student-card');

    cards.forEach(card => {
        const name = card.querySelector('.student-name').textContent.toLowerCase();
        const id = card.querySelector('.student-id').textContent.toLowerCase();
        card.style.display = (name.includes(query) || id.includes(query)) ? 'flex' : 'none';
    });
}

// ─── API Actions ────────────────────────────────────
async function reloadFaces() {
    showToast('info', 'Yükleniyor', 'Yüz verileri yeniden taranıyor...');
    
    try {
        const response = await fetch('/api/reload-faces', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Yüzler Yüklendi', `${data.count} yüz verisi yüklendi`);
            loadAttendance();
        }
    } catch (err) {
        showToast('error', 'Hata', 'Yüz verileri yüklenemedi');
    }
}

async function saveAttendance() {
    try {
        const response = await fetch('/api/attendance/save', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Kaydedildi', data.message);
        }
    } catch (err) {
        showToast('error', 'Hata', 'Yoklama kaydedilemedi');
    }
}

async function downloadPDF() {
    showToast('info', 'PDF Oluşturuluyor', 'Lütfen bekleyin...');
    
    try {
        const response = await fetch('/api/attendance/pdf');
        
        if (!response.ok) throw new Error('PDF oluşturulamadı');
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `yoklama_${new Date().toISOString().slice(0, 10)}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('success', 'PDF İndirildi', 'Yoklama raporu başarıyla oluşturuldu');
    } catch (err) {
        showToast('error', 'Hata', 'PDF oluşturulamadı');
    }
}

async function resetAttendance() {
    if (!confirm('Yoklamayı sıfırlamak istediğinize emin misiniz?')) return;
    
    try {
        const response = await fetch('/api/attendance/reset', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('warning', 'Sıfırlandı', 'Yoklama sıfırlandı');
            loadAttendance();
        }
    } catch (err) {
        showToast('error', 'Hata', 'Yoklama sıfırlanamadı');
    }
}

// ─── Status Badge ───────────────────────────────────
function updateStatus(active) {
    const badge = document.getElementById('status-badge');
    const text = badge.querySelector('.status-text');
    
    if (active) {
        badge.classList.add('active');
        text.textContent = 'Aktif - Taranıyor';
    } else {
        badge.classList.remove('active');
        text.textContent = 'Hazır';
    }
}

// ─── FPS Counter ────────────────────────────────────
function updateFPS() {
    const now = Date.now();
    const elapsed = (now - lastFpsTime) / 1000;
    const fps = Math.round(frameCount / elapsed);
    document.getElementById('fps-counter').textContent = fps;
    frameCount = 0;
    lastFpsTime = now;
}

// ─── Toast Notifications ────────────────────────────
function showToast(type, title, message) {
    const container = document.getElementById('toast-container');
    
    const icons = {
        success: '✓',
        error: '✗',
        info: 'ℹ',
        warning: '⚠'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${icons[type] || 'ℹ'}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    // Otomatik kaldır
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
