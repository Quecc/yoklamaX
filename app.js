/** Kamera önizlemesi, öğrenci listesi ve yoklama işlemleri. */
'use strict';
let cameraActive = false;
let cameraStarting = false;
let videoStream = null;
let recognitionTimer = null;
let fpsInterval = null;
let recognitionController = null;
let frameCount = 0;
let lastFpsTime = Date.now();
let currentFaces = [];

// Eski kamera veya liste isteklerinin yeni oturumu değiştirmesini önler.
let cameraGeneration = 0;
let attendanceRequest = 0;
let serverGeneration = null;

let health = null;
let studentsCache = [];
let attendanceLoaded = false;
let rosterBusy = false;
let resetConfirmationPending = false;
const pendingStudents = new Set();
const busyButtons = new Set();
const $ = (id) => document.getElementById(id);
const video = $('video');
const overlayCanvas = $('overlay-canvas');
const ctx = overlayCanvas.getContext('2d');
const captureCanvas = document.createElement('canvas');

document.addEventListener('DOMContentLoaded', async () => {
    document.querySelectorAll('svg').forEach((icon) => icon.setAttribute('aria-hidden', 'true'));
    for (const [id, handler] of [
        ['btn-camera', toggleCamera],
        ['btn-reload', reloadFaces],
        ['btn-save', saveAttendance],
        ['btn-pdf', downloadPDF],
        ['btn-reset', resetAttendance]
    ])
        $(id).addEventListener('click', handler);
    $('search-input').addEventListener('input', filterStudents);
    $('status-filter').addEventListener('change', filterStudents);
    window.addEventListener('pagehide', () => stopCamera(false));
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) stopCamera(false);
    });
    if (typeof ResizeObserver !== 'undefined')
        new ResizeObserver(() => drawFaceBoxes(currentFaces)).observe($('camera-container'));
    else window.addEventListener('resize', () => drawFaceBoxes(currentFaces));
    updateDateTime();
    setInterval(updateDateTime, 1000);
    await Promise.allSettled([loadHealth(), loadAttendance()]);
});

function updateDateTime() {
    const now = new Date();
    $('current-date').textContent = now.toLocaleDateString('tr-TR', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
    $('current-time').textContent = now.toLocaleTimeString('tr-TR', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Bütün API çağrıları aynı hata, zaman aşımı ve CSRF kontrolünü kullanır.
async function apiRequest(
    path,
    { method = 'GET', body, signal, timeout = 15000, blob = false } = {}
) {
    if (method !== 'GET' && body === undefined) body = {};
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort();
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, timeout);
    const headers = { Accept: blob ? 'application/pdf' : 'application/json' };
    if (method !== 'GET')
        headers['X-CSRF-Token'] = document.querySelector('meta[name="csrf-token"]')?.content || '';
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    try {
        const response = await fetch(path, {
            method,
            headers,
            credentials: 'same-origin',
            cache: 'no-store',
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: controller.signal
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || data.message || `İstek başarısız (${response.status}).`);
        }
        if (blob) {
            if (!response.headers.get('Content-Type')?.includes('application/pdf'))
                throw new Error('Sunucu geçerli bir PDF döndürmedi.');
            return await response.blob();
        }
        const data = await response.json();
        if (data.success === false)
            throw new Error(data.error || data.message || 'İşlem tamamlanamadı.');
        return data;
    } catch (error) {
        if (timedOut) throw new Error('İstek zaman aşımına uğradı. Tekrar deneyin.');
        if (error.name === 'TypeError')
            throw new Error('Sunucuya erişilemiyor. Bağlantıyı kontrol edin.');
        throw error;
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
    }
}

async function loadHealth() {
    try {
        health = await apiRequest('/api/health');
        const manual = !recognitionAvailable(),
            parts = [];
        if (health.demo) parts.push('Örnek liste açık. Listedeki kişiler kurgusaldır.');
        parts.push(
            manual
                ? 'Yoklamayı listeden alabilirsiniz. Yüz tanıma şu anda kullanılamıyor; kamerayı açarsanız yalnızca önizleme gösterilir.'
                : 'Yüz tanıma hazır. Kamera açıkken eşleşen öğrenciler listede “var” olarak işaretlenir.'
        );
        if (health.recognition?.error) parts.push(String(health.recognition.error));
        const skipped = health.recognition?.skipped;
        if (Array.isArray(skipped) && skipped.length)
            parts.push(`${skipped.length} fotoğraf yüz kaydına alınamadı.`);
        $('mode-banner').textContent = parts.join(' ');
        $('mode-banner').classList.toggle('manual', manual);
        $('camera-placeholder').querySelector('p').textContent = 'Kamera kapalı';
        $('camera-placeholder').querySelector('.camera-hint').textContent = manual
            ? 'Önizleme için “Kamerayı Başlat” düğmesini kullanın.'
            : 'Başlat düğmesine basın ve tarayıcınız isterse kamera iznini verin.';
        $('camera-help').textContent = manual
            ? 'Önizleme görüntüsü tanıma için sunucuya gönderilmez. Öğrencilerin durumunu listeden değiştirebilirsiniz.'
            : 'Eşleşen öğrenciler “var” olarak işaretlenir. Sonuçları listeden kontrol edip düzeltebilirsiniz.';
    } catch (error) {
        health = null;
        $('mode-banner').textContent = `Sistem durumu alınamadı. ${error.message}`;
        $('mode-banner').classList.add('manual');
    } finally {
        updateStatus();
        updateControls();
    }
}
function recognitionAvailable() {
    return health?.mode !== 'manual' && health?.recognition?.available === true;
}
function updateStatus() {
    const badge = $('status-badge');
    badge.classList.toggle('active', cameraActive);
    let message = 'Kamera kapalı';
    if (cameraActive) {
        message = recognitionAvailable()
            ? 'Kamera açık · Yoklama alınıyor'
            : 'Kamera açık · Önizleme';
    } else if (cameraStarting) {
        message = 'Kamera açılıyor';
    } else if (!health) {
        message = 'Bağlantı bekleniyor';
    }
    badge.querySelector('.status-text').textContent = message;
}
function updateControls() {
    $('btn-camera').disabled =
        rosterBusy ||
        pendingStudents.size > 0 ||
        (!cameraStarting && !cameraActive && (!health || !attendanceLoaded));
    $('btn-camera').title = recognitionAvailable()
        ? 'Kamera ve otomatik yüz tanıma'
        : 'Yerel kamera önizlemesi. Yoklamayı listeden işaretleyin.';
    $('btn-reload').disabled = rosterBusy || pendingStudents.size > 0;
    for (const id of ['btn-save', 'btn-pdf', 'btn-reset'])
        $(id).disabled =
            rosterBusy ||
            pendingStudents.size > 0 ||
            !attendanceLoaded ||
            !studentsCache.length ||
            busyButtons.has(id);
    $('student-list')
        .querySelectorAll('.student-card')
        .forEach((card) => {
            card.disabled = rosterBusy || pendingStudents.has(card.dataset.id);
        });
}
function withTimeout(promise, timeout, message) {
    let timer;
    return Promise.race([
        promise,
        new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error(message)), timeout);
        })
    ]).finally(() => clearTimeout(timer));
}
async function toggleCamera() {
    if (cameraActive || cameraStarting) stopCamera();
    else await startCamera();
}
async function startCamera() {
    if (
        cameraActive ||
        cameraStarting ||
        !health ||
        !attendanceLoaded ||
        rosterBusy ||
        pendingStudents.size
    )
        return;
    const generation = ++cameraGeneration;
    cameraStarting = true;
    $('btn-camera').querySelector('span').textContent = 'İptal';
    updateStatus();
    try {
        if (!navigator.mediaDevices?.getUserMedia)
            throw new Error(
                'Kamera için localhost veya HTTPS ve kamera destekli bir tarayıcı gerekir.'
            );
        const requestedStream = navigator.mediaDevices
            .getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user'
                },
                audio: false
            })
            .then((stream) => {
                // İzin penceresi, kullanıcı kamerayı iptal ettikten sonra da sonuçlanabilir.
                if (generation !== cameraGeneration) {
                    stream.getTracks().forEach((track) => track.stop());
                    throw new DOMException('Kamera isteği iptal edildi.', 'AbortError');
                }
                return stream;
            });
        const stream = await withTimeout(
            requestedStream,
            20000,
            'Kamera izni zaman aşımına uğradı. Tekrar deneyin.'
        );
        if (generation !== cameraGeneration) {
            stream.getTracks().forEach((track) => track.stop());
            return;
        }
        videoStream = stream;
        video.srcObject = videoStream;
        await withTimeout(video.play(), 10000, 'Kamera görüntüsü başlatılamadı.');
        if (generation !== cameraGeneration) return;
        if (!video.videoWidth || !video.videoHeight)
            throw new Error('Kameradan geçerli görüntü alınamadı.');
        videoStream.getTracks().forEach((track) =>
            track.addEventListener(
                'ended',
                () => {
                    if (generation === cameraGeneration) {
                        stopCamera(false);
                        showToast(
                            'warning',
                            'Kamera durdu',
                            'Kamera bağlantısını ve tarayıcı izinlerini kontrol edin.'
                        );
                    }
                },
                { once: true }
            )
        );
        cameraStarting = false;
        cameraActive = true;
        frameCount = 0;
        lastFpsTime = Date.now();
        $('camera-container').classList.add('active');
        $('btn-camera').classList.add('active');
        $('btn-camera').setAttribute('aria-pressed', 'true');
        $('btn-camera').querySelector('span').textContent = 'Kamerayı Durdur';
        updateStatus();
        showToast(
            'success',
            'Kamera açıldı',
            recognitionAvailable()
                ? 'Otomatik yüz tanıma başladı.'
                : 'Yerel önizleme başladı. Yoklamayı listeden işaretleyin.'
        );
        if (recognitionAvailable()) {
            fpsInterval = setInterval(updateFPS, 1000);
            captureAndRecognize(generation);
        }
    } catch (error) {
        if (generation !== cameraGeneration) return;
        stopCamera(false);
        const message =
            error.name === 'NotAllowedError'
                ? 'Kamera izni verilmedi. Tarayıcı izinlerini kontrol edin.'
                : error.name === 'NotFoundError'
                  ? 'Kamera bulunamadı. Bir kamera bağlayın.'
                  : error.name === 'NotReadableError'
                    ? 'Kamera başka bir uygulamada kullanılıyor olabilir.'
                    : error.message;
        showToast('error', 'Kamera açılamadı', message);
    } finally {
        updateControls();
    }
}
function stopCamera(notify = true) {
    const wasRunning = cameraActive || cameraStarting;
    ++cameraGeneration;
    cameraActive = false;
    cameraStarting = false;
    clearTimeout(recognitionTimer);
    clearInterval(fpsInterval);
    recognitionTimer = null;
    fpsInterval = null;
    recognitionController?.abort();
    recognitionController = null;
    videoStream?.getTracks().forEach((track) => track.stop());
    videoStream = null;
    video.srcObject = null;
    currentFaces = [];
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    $('camera-container').classList.remove('active');
    $('btn-camera').classList.remove('active');
    $('btn-camera').setAttribute('aria-pressed', 'false');
    $('btn-camera').querySelector('span').textContent = 'Kamerayı Başlat';
    for (const id of ['face-count', 'recognized-count', 'fps-counter']) $(id).textContent = '0';
    updateStatus();
    updateControls();
    if (notify && wasRunning)
        showToast('info', 'Kamera kapatıldı', 'Kamera önizlemesi ve varsa yüz tanıma durduruldu.');
}
async function captureAndRecognize(generation = cameraGeneration) {
    if (
        !cameraActive ||
        !recognitionAvailable() ||
        generation !== cameraGeneration ||
        recognitionController ||
        rosterBusy
    )
        return;
    const controller = new AbortController();
    recognitionController = controller;
    try {
        captureCanvas.width = video.videoWidth;
        captureCanvas.height = video.videoHeight;
        captureCanvas.getContext('2d').drawImage(video, 0, 0);
        const result = await apiRequest('/api/recognize', {
            method: 'POST',
            body: {
                image: captureCanvas.toDataURL('image/jpeg', 0.65),
                generation: serverGeneration
            },
            signal: controller.signal,
            timeout: 30000
        });
        if (!cameraActive || generation !== cameraGeneration) return;
        frameCount++;
        currentFaces = Array.isArray(result.faces) ? result.faces : [];
        drawFaceBoxes(currentFaces);
        $('face-count').textContent = currentFaces.length;
        $('recognized-count').textContent = currentFaces.filter((face) => face.matched).length;
        for (const name of result.newly_marked || [])
            showToast('success', 'Öğrenci tanındı', `${name} yoklamaya eklendi.`);
        if (Array.isArray(result.attendance)) updateAttendanceUI(result.attendance);
    } catch (error) {
        if (generation !== cameraGeneration || error.name === 'AbortError') return;
        stopCamera(false);
        showToast(
            'error',
            'Yüz tanıma durduruldu',
            `${error.message} Kamerayı yeniden başlatabilirsiniz.`
        );
    } finally {
        if (recognitionController === controller) recognitionController = null;
        if (cameraActive && recognitionAvailable() && generation === cameraGeneration)
            recognitionTimer = setTimeout(() => captureAndRecognize(generation), 600);
    }
}
// Yüz kutularını, aynalı görüntünün kenar boşluklarını da hesaba katarak yerleştirir.
function displayedBox(box, sourceWidth, sourceHeight, viewWidth, viewHeight, mirrored = true) {
    if (
        !box ||
        ![
            box.top,
            box.right,
            box.bottom,
            box.left,
            sourceWidth,
            sourceHeight,
            viewWidth,
            viewHeight
        ].every(Number.isFinite) ||
        sourceWidth <= 0 ||
        sourceHeight <= 0 ||
        viewWidth <= 0 ||
        viewHeight <= 0 ||
        box.right <= box.left ||
        box.bottom <= box.top
    )
        return null;
    const scale = Math.min(viewWidth / sourceWidth, viewHeight / sourceHeight),
        offsetX = (viewWidth - sourceWidth * scale) / 2,
        offsetY = (viewHeight - sourceHeight * scale) / 2;
    return {
        left: offsetX + (mirrored ? sourceWidth - box.right : box.left) * scale,
        right: offsetX + (mirrored ? sourceWidth - box.left : box.right) * scale,
        top: offsetY + box.top * scale,
        bottom: offsetY + box.bottom * scale
    };
}
function drawFaceBoxes(faces) {
    const { width, height } = $('camera-container').getBoundingClientRect();
    if (!width || !height || !cameraActive) return;
    const pixelRatio = window.devicePixelRatio || 1;
    overlayCanvas.width = Math.round(width * pixelRatio);
    overlayCanvas.height = Math.round(height * pixelRatio);
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    for (const face of faces) {
        const box = displayedBox(face.box, video.videoWidth, video.videoHeight, width, height);
        if (!box) continue;
        ctx.strokeStyle = face.matched ? '#14853b' : '#f5b942';
        ctx.lineWidth = 2;
        ctx.strokeRect(box.left, box.top, box.right - box.left, box.bottom - box.top);
        // Eşleşme mesafesi bir doğruluk yüzdesi olmadığı için yüzde göstermiyoruz.
        const label = face.matched ? String(face.name || 'Tanınan öğrenci') : 'Bilinmeyen';
        ctx.font = '600 13px -apple-system, sans-serif';
        const labelWidth = Math.min(ctx.measureText(label).width + 16, width),
            x = Math.max(0, Math.min(box.left, width - labelWidth)),
            y = Math.max(0, box.top - 26);
        ctx.fillStyle = face.matched ? '#14853b' : '#f5b942';
        ctx.fillRect(x, y, labelWidth, 24);
        ctx.fillStyle = face.matched ? '#fff' : '#1d1d1f';
        ctx.fillText(label, x + 8, y + 17, labelWidth - 16);
    }
}
async function loadAttendance() {
    const request = ++attendanceRequest;
    $('student-list').setAttribute('aria-busy', 'true');
    $('list-feedback').textContent = 'Liste yükleniyor…';
    try {
        const data = await apiRequest('/api/attendance');
        if (request !== attendanceRequest) return;
        if (!Array.isArray(data.students))
            throw new Error('Sunucu geçerli bir öğrenci listesi döndürmedi.');
        serverGeneration = data.generation ?? serverGeneration;
        attendanceLoaded = true;
        updateAttendanceUI(data.students);
        $('list-feedback').textContent = '';
    } catch (error) {
        if (request !== attendanceRequest) return;
        $('list-feedback').textContent = `${error.message} “Listeyi yenile” ile tekrar deneyin.`;
        if (!attendanceLoaded)
            $('student-list').replaceChildren(
                createEmptyState('Liste yüklenemedi', 'Sunucu bağlantısını kontrol edin.')
            );
    } finally {
        if (request === attendanceRequest) $('student-list').setAttribute('aria-busy', 'false');
        updateControls();
    }
}
function element(tag, className, text) {
    // API'den gelen adları HTML olarak yorumlamadan ekrana yazarız.
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}
function createStudentCard(student) {
    const card = element('button', 'student-card');
    card.type = 'button';
    card.dataset.id = String(student.id);
    const avatar = element('span', 'student-avatar');
    avatar.setAttribute('aria-hidden', 'true');
    const initials = element('span', 'student-initials');
    avatar.append(initials);
    const info = element('span', 'student-info'),
        name = element('span', 'student-name'),
        id = element('span', 'student-id');
    info.append(name, id);
    const status = element('span', 'student-status'),
        statusIcon = element('span', 'status-icon'),
        statusLabel = element('span', 'status-label'),
        time = element('span', 'status-time');
    statusIcon.setAttribute('aria-hidden', 'true');
    status.append(statusIcon, statusLabel, time);
    card.append(avatar, info, status);
    card.parts = {
        avatar,
        initials,
        photo: null,
        photoUrl: '',
        name,
        id,
        statusIcon,
        statusLabel,
        time
    };
    card.addEventListener('click', () => toggleStudentStatus(card.dataset.id));
    updateStudentCard(card, student);
    return card;
}
function updateStudentCard(card, student) {
    const present = student.status === 'present',
        name = String(student.name || 'İsimsiz öğrenci'),
        id = String(student.id);
    card.dataset.status = present ? 'present' : 'absent';
    card.classList.toggle('present', present);
    card.classList.toggle('absent', !present);
    card.setAttribute('aria-pressed', String(present));
    card.setAttribute(
        'aria-label',
        `${name}, numara ${id}, ${present ? 'var' : 'yok'}. ${present ? 'Yok' : 'Var'} olarak işaretle.`
    );
    card.parts.initials.textContent = name
        .trim()
        .split(/\s+/)
        .map((part) => Array.from(part)[0])
        .slice(0, 2)
        .join('')
        .toLocaleUpperCase('tr-TR');
    updateStudentPhoto(card, student, name);
    card.parts.name.textContent = name;
    card.parts.id.textContent = `#${id}`;
    card.parts.statusIcon.textContent = present ? '✓' : '–';
    card.parts.statusLabel.textContent = present ? 'Var' : 'Yok';
    card.parts.time.textContent = present
        ? [student.time, student.auto ? 'Kamera' : 'Elle'].filter(Boolean).join(' · ')
        : '';
}
function safePhotoUrl(url, studentId) {
    const id = String(studentId);
    return /^\d+$/.test(id) && typeof url === 'string' && url === `/api/students/${id}/photo`
        ? url
        : '';
}
function updateStudentPhoto(card, student, name) {
    const url = safePhotoUrl(student.photo_url, student.id);
    const parts = card.parts;
    if (parts.photoUrl !== url) {
        parts.photo?.remove();
        parts.photo = null;
        parts.photoUrl = url;
        parts.initials.hidden = false;
        if (url) {
            const photo = element('img', 'student-photo');
            photo.alt = `${name} portresi`;
            photo.loading = 'lazy';
            photo.decoding = 'async';
            photo.width = 44;
            photo.height = 44;
            photo.addEventListener('load', () => {
                if (parts.photo === photo) parts.initials.hidden = true;
            });
            photo.addEventListener('error', () => {
                if (parts.photo !== photo) return;
                photo.remove();
                parts.photo = null;
                parts.initials.hidden = false;
            });
            parts.photo = photo;
            parts.avatar.append(photo);
            photo.src = url;
        }
    }
    if (parts.photo) parts.photo.alt = `${name} portresi`;
}
function createEmptyState(
    title = 'Öğrenci kaydı yok',
    hint = 'Fotoğraf klasörüne numara_ad_soyad.jpg biçiminde fotoğraf ekleyip “Listeyi yenile” düğmesine basın. Ayrıntılar fotoğraf ekleme kılavuzunda.'
) {
    const state = element('div', 'empty-state');
    state.append(element('p', '', title), element('span', '', hint));
    return state;
}
function updateAttendanceUI(students) {
    studentsCache = students;
    const list = $('student-list');
    const focusedId = document.activeElement?.classList?.contains('student-card')
        ? document.activeElement.dataset.id
        : null;
    const existing = new Map(
        Array.from(list.querySelectorAll('.student-card'), (card) => [card.dataset.id, card])
    );
    const nodes = students.map((student) => {
        const card = existing.get(String(student.id)) || createStudentCard(student);
        updateStudentCard(card, student);
        return card;
    });
    list.replaceChildren(...(nodes.length ? nodes : [createEmptyState()]));
    const present = students.filter((student) => student.status === 'present').length;
    updateStats({
        total: students.length,
        present,
        absent: students.length - present,
        rate: students.length ? (present / students.length) * 100 : 0
    });
    filterStudents();
    updateControls();
    if (focusedId) {
        const focusedCard = nodes.find((card) => card.dataset.id === focusedId && !card.hidden);
        (focusedCard || $('status-filter')).focus({ preventScroll: true });
    }
}
function updateStats(stats) {
    for (const [suffix, label] of [
        ['total', 'Toplam'],
        ['present', 'Var'],
        ['absent', 'Yok']
    ]) {
        const value = Number(stats[suffix]) || 0;
        $(`badge-${suffix}`).textContent = `${label} ${value}`;
        $(`badge-${suffix}`).setAttribute('aria-label', `${label}: ${value}`);
    }
    const rate = Math.min(100, Math.max(0, Number(stats.rate) || 0)),
        formatted = new Intl.NumberFormat('tr-TR', {
            maximumFractionDigits: 1
        }).format(rate);
    $('progress-fill').style.width = `${rate}%`;
    $('progress-bar').setAttribute('aria-valuenow', String(rate));
    $('progress-text').textContent = `%${formatted} katılım`;
}
function filterStudents() {
    const list = $('student-list');
    const query = $('search-input').value.trim().toLocaleLowerCase('tr-TR');
    const selectedStatus = $('status-filter').value;
    const cards = Array.from(list.querySelectorAll('.student-card'));
    let visible = 0;

    for (const card of cards) {
        const text = `${card.parts.name.textContent} ${card.dataset.id}`.toLocaleLowerCase('tr-TR');
        const matchesName = text.includes(query);
        const matchesStatus =
            !['present', 'absent'].includes(selectedStatus) ||
            card.dataset.status === selectedStatus;
        card.hidden = !matchesName || !matchesStatus;
        if (!card.hidden) visible++;
    }

    list.querySelector('.search-empty')?.remove();
    if (cards.length && !visible) {
        const title = query ? 'Aramayla eşleşen öğrenci yok' : 'Bu durumda öğrenci yok';
        const empty = createEmptyState(
            title,
            'Aramayı temizleyin veya durum filtresinden “Tümü” seçeneğini seçin.'
        );
        empty.classList.add('search-empty');
        list.append(empty);
    }

    const summary = `${cards.length} öğrenciden ${visible} kişi gösteriliyor.`;
    if ($('filter-summary').textContent !== summary) $('filter-summary').textContent = summary;
}
async function toggleStudentStatus(studentId) {
    if (rosterBusy || pendingStudents.has(studentId)) return;
    const restoreFocus = document.activeElement?.dataset?.id === studentId;
    // Elle düzeltme sırasında kamera taraması durur; kullanıcı sonucu rahatça kontrol eder.
    if (cameraActive || cameraStarting) stopCamera();
    pendingStudents.add(studentId);
    ++attendanceRequest;
    updateControls();
    try {
        const data = await apiRequest('/api/attendance/toggle', {
            method: 'POST',
            body: { id: studentId }
        });
        await loadAttendance();
        showToast(
            'info',
            'Yoklama güncellendi',
            `${data.student.name}: ${data.student.status === 'present' ? 'var' : 'yok'}`
        );
    } catch (error) {
        showToast('error', 'Durum güncellenemedi', error.message);
    } finally {
        pendingStudents.delete(studentId);
        updateControls();
        if (restoreFocus)
            Array.from($('student-list').querySelectorAll('.student-card'))
                .find((card) => card.dataset.id === studentId && !card.hidden)
                ?.focus({ preventScroll: true });
    }
}
async function reloadFaces() {
    if (rosterBusy || pendingStudents.size) return;
    rosterBusy = true;
    stopCamera(false);
    ++attendanceRequest;
    updateControls();
    $('list-feedback').textContent = 'Kayıtlar yeniden taranıyor…';
    try {
        const data = await apiRequest('/api/reload-faces', {
            method: 'POST',
            timeout: 120000
        });
        await Promise.allSettled([loadAttendance(), loadHealth()]);
        showToast(
            'success',
            'Liste yenilendi',
            `${data.count} öğrenci kaydı yüklendi. Mevcut yoklama korunur.`
        );
    } catch (error) {
        $('list-feedback').textContent = error.message;
        showToast('error', 'Liste yenilenemedi', error.message);
    } finally {
        rosterBusy = false;
        updateControls();
    }
}
async function saveAttendance() {
    if ($('btn-save').disabled) return;
    busyButtons.add('btn-save');
    updateControls();
    try {
        const data = await apiRequest('/api/attendance/save', {
            method: 'POST'
        });
        showToast('success', 'Kaydedildi', data.message || 'Yoklama kaydı oluşturuldu.');
    } catch (error) {
        showToast('error', 'Yoklama kaydedilemedi', error.message);
    } finally {
        busyButtons.delete('btn-save');
        updateControls();
    }
}
async function downloadPDF() {
    if ($('btn-pdf').disabled) return;
    busyButtons.add('btn-pdf');
    updateControls();
    showToast('info', 'PDF hazırlanıyor', 'Lütfen bekleyin…');
    try {
        const blob = await apiRequest('/api/attendance/pdf', { blob: true }),
            url = URL.createObjectURL(blob),
            link = element('a'),
            date = new Date();
        const dateName = [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, '0'),
            String(date.getDate()).padStart(2, '0')
        ].join('-');
        link.href = url;
        link.download = `yoklama_${dateName}.pdf`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showToast('success', 'PDF hazır', 'Yoklama raporu indirildi.');
    } catch (error) {
        showToast('error', 'PDF oluşturulamadı', error.message);
    } finally {
        busyButtons.delete('btn-pdf');
        updateControls();
    }
}
async function resetAttendance() {
    if (rosterBusy || pendingStudents.size || resetConfirmationPending || $('btn-reset').disabled)
        return;
    if (!(await confirmReset())) return;
    rosterBusy = true;
    stopCamera(false);
    ++attendanceRequest;
    updateControls();
    try {
        await apiRequest('/api/attendance/reset', { method: 'POST' });
        await loadAttendance();
        showToast(
            'success',
            'Yeni yoklama hazır',
            'Önceki yoklama arşivlendi. Kamerayı açabilir veya listeden işaretleyebilirsiniz.'
        );
    } catch (error) {
        showToast('error', 'Yeni yoklama başlatılamadı', error.message);
    } finally {
        rosterBusy = false;
        updateControls();
    }
}
function confirmReset() {
    if (resetConfirmationPending) return Promise.resolve(false);
    resetConfirmationPending = true;
    const dialog = $('reset-dialog');
    dialog.returnValue = 'cancel';
    return new Promise((resolve) => {
        const finish = () => {
            dialog.removeEventListener('close', finish);
            dialog.removeEventListener('cancel', cancel);
            dialog.removeEventListener('click', dismiss);
            resetConfirmationPending = false;
            resolve(dialog.returnValue === 'confirm');
        };
        const cancel = (event) => {
            event.preventDefault();
            dialog.close('cancel');
        };
        const dismiss = (event) => {
            if (event.target !== dialog) return;
            const bounds = dialog.getBoundingClientRect();
            if (
                event.clientX < bounds.left ||
                event.clientX > bounds.right ||
                event.clientY < bounds.top ||
                event.clientY > bounds.bottom
            )
                dialog.close('cancel');
        };
        dialog.addEventListener('close', finish);
        dialog.addEventListener('cancel', cancel);
        dialog.addEventListener('click', dismiss);
        dialog.showModal();
        $('btn-reset-cancel').focus();
    });
}
function updateFPS() {
    const now = Date.now(),
        elapsed = (now - lastFpsTime) / 1000;
    $('fps-counter').textContent = elapsed > 0 ? (frameCount / elapsed).toFixed(1) : '0';
    frameCount = 0;
    lastFpsTime = now;
}
function showToast(type, title, message) {
    const icons = { success: '✓', error: '✗', info: 'ℹ', warning: '⚠' },
        safeType = Object.hasOwn(icons, type) ? type : 'info';
    const toast = element('div', `toast ${safeType}`),
        icon = element('span', 'toast-icon', icons[safeType]),
        content = element('div', 'toast-content');
    icon.setAttribute('aria-hidden', 'true');
    content.append(element('p', 'toast-title', title), element('p', 'toast-message', message));
    toast.append(icon, content);
    const container = $('toast-container');
    while (container.children.length >= 4) container.firstElementChild.remove();
    container.append(toast);
    setTimeout(
        () => {
            toast.classList.add('hiding');
            setTimeout(() => toast.remove(), 300);
        },
        safeType === 'error' ? 8000 : 4500
    );
}
