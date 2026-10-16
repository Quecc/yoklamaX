'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Small DOM double: assigning innerHTML fails, so untrusted markup cannot slip
// through these regression tests. Real layout/flows are also checked in-browser.
function harness() {
    let document;
    class Node {
        constructor(tag = 'div') {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.style = {};
            this.listeners = {};
            this.className = '';
            this.value = '';
            this._text = '';
        }
        set textContent(text) {
            this._text = String(text);
            this.children = [];
        }
        get textContent() {
            return this._text + this.children.map((child) => child.textContent).join('');
        }
        set innerHTML(_) {
            throw new Error('Unsafe innerHTML assignment');
        }
        get classList() {
            const node = this;
            return {
                contains(name) {
                    return node.className.split(/\s+/).includes(name);
                },
                add(name) {
                    if (!this.contains(name)) node.className += ` ${name}`;
                },
                remove(name) {
                    node.className = node.className
                        .split(/\s+/)
                        .filter((item) => item !== name)
                        .join(' ');
                },
                toggle(name, active) {
                    if (active) this.add(name);
                    else this.remove(name);
                }
            };
        }
        setAttribute(name, value) {
            this.attributes[name] = String(value);
        }
        getAttribute(name) {
            return this.attributes[name];
        }
        append(...nodes) {
            for (const node of nodes) {
                node.remove();
                node.parentNode = this;
                this.children.push(node);
            }
        }
        replaceChildren(...nodes) {
            for (const child of this.children) child.parentNode = null;
            this.children = [];
            this._text = '';
            this.append(...nodes);
        }
        remove() {
            if (this.parentNode)
                this.parentNode.children = this.parentNode.children.filter(
                    (child) => child !== this
                );
            this.parentNode = null;
        }
        querySelectorAll(selector) {
            return this.children.flatMap((child) => [
                ...((
                    selector.startsWith('.')
                        ? child.classList.contains(selector.slice(1))
                        : child.tagName === selector.toUpperCase()
                )
                    ? [child]
                    : []),
                ...child.querySelectorAll(selector)
            ]);
        }
        querySelector(selector) {
            return this.querySelectorAll(selector)[0] || null;
        }
        get firstElementChild() {
            return this.children[0];
        }
        addEventListener(name, listener) {
            this.listeners[name] = listener;
        }
        removeEventListener(name, listener) {
            if (this.listeners[name] === listener) delete this.listeners[name];
        }
        showModal() {
            this.open = true;
            this.modalCount = (this.modalCount || 0) + 1;
        }
        close(value) {
            this.returnValue = value;
            this.open = false;
            this.listeners.close?.({ target: this });
        }
        focus() {
            document.activeElement = this;
        }
        getBoundingClientRect() {
            return {
                left: 0,
                top: 0,
                right: 640,
                bottom: 480,
                width: 640,
                height: 480
            };
        }
        getContext() {
            return {
                clearRect() {},
                drawImage() {},
                setTransform() {},
                strokeRect() {},
                fillRect() {},
                fillText() {},
                measureText() {
                    return { width: 60 };
                }
            };
        }
        toDataURL() {
            return 'data:image/jpeg;base64,AA==';
        }
        play() {
            return Promise.resolve();
        }
    }
    const ids = new Map();
    for (const id of [
        'video',
        'overlay-canvas',
        'status-badge',
        'mode-banner',
        'camera-placeholder',
        'camera-container',
        'camera-help',
        'btn-camera',
        'btn-reload',
        'btn-save',
        'btn-pdf',
        'btn-reset',
        'reset-dialog',
        'btn-reset-cancel',
        'btn-reset-confirm',
        'student-list',
        'list-feedback',
        'search-input',
        'status-filter',
        'filter-summary',
        'face-count',
        'recognized-count',
        'fps-counter',
        'badge-total',
        'badge-present',
        'badge-absent',
        'progress-fill',
        'progress-bar',
        'progress-text',
        'toast-container'
    ])
        ids.set(id, new Node());
    ids.get('video').videoWidth = 1280;
    ids.get('video').videoHeight = 720;
    const status = new Node('span');
    status.className = 'status-text';
    ids.get('status-badge').append(status);
    ids.get('btn-camera').append(new Node('span'));
    const hint = new Node('span');
    hint.className = 'camera-hint';
    ids.get('camera-placeholder').append(new Node('p'), hint);
    document = {
        body: new Node('body'),
        getElementById: (id) => ids.get(id),
        createElement: (tag) => new Node(tag),
        addEventListener() {},
        querySelector: () => ({ content: 'test-csrf' }),
        querySelectorAll: () => []
    };
    let timerId = 0;
    const timers = new Map();
    const context = vm.createContext({
        document,
        window: { addEventListener() {}, devicePixelRatio: 1 },
        navigator: {},
        DOMException,
        AbortController,
        Intl,
        console,
        setTimeout: (callback) => {
            const id = ++timerId;
            timers.set(id, callback);
            return id;
        },
        clearTimeout: (id) => timers.delete(id),
        setInterval: () => 1,
        clearInterval() {},
        fetch: async () => ({ ok: true, json: async () => ({}) })
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8'), context);
    return {
        context,
        ids,
        document,
        timers,
        state: (expression) => vm.runInContext(expression, context)
    };
}

test('student and notification markup remains literal text', () => {
    const { context, ids } = harness();
    const payload = '<img src=x onerror=alert(1)>';
    const card = context.createStudentCard({
        id: '\" onclick=alert(2)',
        name: payload,
        status: 'present',
        time: payload
    });
    assert.equal(card.parts.name.textContent, payload);
    assert.equal(card.parts.time.textContent, `${payload} · Elle`);
    assert.equal(card.querySelectorAll('img').length, 0);
    context.showToast('success', payload, payload);
    assert.ok(ids.get('toast-container').textContent.includes(payload));
    assert.equal(ids.get('toast-container').querySelectorAll('img').length, 0);
});

test('attendance cards are keyboard buttons with explicit state', () => {
    const { context } = harness();
    const card = context.createStudentCard({
        id: '20001',
        name: 'İpek Yılmaz',
        status: 'absent'
    });
    assert.equal(card.tagName, 'BUTTON');
    assert.equal(card.type, 'button');
    assert.equal(card.getAttribute('aria-pressed'), 'false');
    assert.match(card.getAttribute('aria-label'), /Var olarak işaretle/);
    context.updateStudentCard(card, {
        id: '20001',
        name: 'İpek Yılmaz',
        status: 'present',
        auto: true,
        time: '09:30'
    });
    assert.equal(card.getAttribute('aria-pressed'), 'true');
    assert.match(card.parts.time.textContent, /Kamera/);
});

test('refresh preserves Turkish search, focus and empty search feedback', () => {
    const { context, ids, document } = harness();
    const students = [
        { id: '1', name: 'İpek', status: 'absent' },
        { id: '2', name: 'Ali', status: 'absent' }
    ];
    ids.get('search-input').value = 'ipek';
    context.updateAttendanceUI(students);
    const first = ids.get('student-list').children[0];
    first.focus();
    assert.equal(first.hidden, false);
    assert.equal(ids.get('student-list').children[1].hidden, true);
    context.updateAttendanceUI([{ ...students[0], status: 'present' }, students[1]]);
    assert.equal(document.activeElement, first);
    assert.equal(ids.get('student-list').children[1].hidden, true);
    ids.get('search-input').value = 'bulunmuyor';
    context.filterStudents();
    assert.match(
        ids.get('student-list').querySelector('.search-empty').textContent,
        /eşleşen öğrenci yok/
    );
});

test('status filter combines with Turkish search and does not change attendance totals', () => {
    const { context, ids } = harness();
    context.updateAttendanceUI([
        { id: '1', name: 'İpek', status: 'present' },
        { id: '2', name: 'İpek Yılmaz', status: 'absent' },
        { id: '3', name: 'Ali', status: 'absent' }
    ]);
    ids.get('search-input').value = 'ipek';
    ids.get('status-filter').value = 'absent';
    context.filterStudents();

    const visible = ids
        .get('student-list')
        .querySelectorAll('.student-card')
        .filter((card) => !card.hidden);
    assert.deepEqual(
        visible.map((card) => card.dataset.id),
        ['2']
    );
    assert.equal(ids.get('badge-total').textContent, 'Toplam 3');
    assert.equal(ids.get('badge-present').textContent, 'Var 1');
    assert.equal(ids.get('badge-absent').textContent, 'Yok 2');
    assert.match(ids.get('filter-summary').textContent, /3 öğrenciden 1 kişi/);
});

test('an updated student leaving the status filter moves keyboard focus to the filter', () => {
    const { context, ids, document } = harness();
    ids.get('status-filter').value = 'absent';
    context.updateAttendanceUI([{ id: '1', name: 'Ali', status: 'absent' }]);
    const card = ids.get('student-list').children[0];
    card.focus();

    context.updateAttendanceUI([{ id: '1', name: 'Ali', status: 'present' }]);
    assert.equal(card.hidden, true);
    assert.equal(ids.get('status-filter').value, 'absent');
    assert.equal(document.activeElement, ids.get('status-filter'));
    assert.match(
        ids.get('student-list').querySelector('.search-empty').textContent,
        /Bu durumda öğrenci yok/
    );
    assert.match(ids.get('filter-summary').textContent, /1 öğrenciden 0 kişi/);

    ids.get('status-filter').value = 'all';
    context.filterStudents();
    assert.equal(card.hidden, false);
    assert.equal(ids.get('student-list').querySelector('.search-empty'), null);
});

test('POSTs carry CSRF and credentials; HTTP error is surfaced', async () => {
    const { context } = harness();
    let sent;
    context.fetch = async (_, options) => {
        sent = options;
        return { ok: true, json: async () => ({ success: true }) };
    };
    await context.apiRequest('/api/attendance/toggle', {
        method: 'POST',
        body: { id: '001' }
    });
    assert.equal(sent.headers['X-CSRF-Token'], 'test-csrf');
    assert.equal(sent.credentials, 'same-origin');
    assert.equal(sent.body, '{"id":"001"}');
    await context.apiRequest('/api/attendance/save', { method: 'POST' });
    assert.equal(sent.body, '{}');
    assert.equal(sent.headers['Content-Type'], 'application/json');
    context.fetch = async () => ({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Öğrenci bulunamadı' })
    });
    await assert.rejects(
        context.apiRequest('/api/attendance/toggle', { method: 'POST' }),
        /Öğrenci bulunamadı/
    );
});

test('face boxes follow mirrored contain video and letterboxing', () => {
    const { context } = harness();
    const box = { left: 128, right: 256, top: 72, bottom: 144 };
    assert.deepEqual(JSON.parse(JSON.stringify(context.displayedBox(box, 1280, 720, 640, 480))), {
        left: 512,
        right: 576,
        top: 96,
        bottom: 132
    });
    assert.equal(context.displayedBox(box, 1280, 720, 640, 480, false).left, 64);
    assert.equal(context.displayedBox(box, 0, 720, 640, 480), null);
});

test('late recognition response after stop cannot change attendance', async () => {
    const { context, ids, state } = harness();
    let resolve;
    context.fetch = () =>
        new Promise((done) => {
            resolve = done;
        });
    state(
        'cameraActive = true; cameraGeneration = 3; serverGeneration = 7; health = {mode:"recognition", recognition:{available:true}};'
    );
    context.updateAttendanceUI([{ id: '1', name: 'Ali', status: 'absent' }]);
    const pending = context.captureAndRecognize();
    context.stopCamera(false);
    resolve({
        ok: true,
        json: async () => ({
            faces: [{ matched: true }],
            attendance: [{ id: '1', name: 'Ali', status: 'present' }]
        })
    });
    await pending;
    assert.equal(state('studentsCache[0].status'), 'absent');
    assert.equal(ids.get('recognized-count').textContent, '0');
    assert.equal(state('recognitionTimer'), null);
});

test('camera tracks are released when video playback fails', async () => {
    const { context, ids, state } = harness();
    let stopped = 0;
    context.navigator.mediaDevices = {
        getUserMedia: async () => ({
            getTracks: () => [{ stop: () => stopped++, addEventListener() {} }]
        })
    };
    ids.get('video').play = async () => {
        throw new Error('play failed');
    };
    state('health = {mode:"recognition", recognition:{available:true}}; attendanceLoaded = true;');
    await context.startCamera();
    assert.equal(stopped, 1);
    assert.equal(ids.get('video').srcObject, null);
    assert.equal(state('cameraActive'), false);
});

test('permission granted after camera cancellation releases its stream', async () => {
    const { context, state } = harness();
    let resolve,
        stopped = 0;
    context.navigator.mediaDevices = {
        getUserMedia: () =>
            new Promise((done) => {
                resolve = done;
            })
    };
    state('health = {mode:"recognition", recognition:{available:true}}; attendanceLoaded = true;');
    const starting = context.startCamera();
    context.stopCamera(false);
    resolve({ getTracks: () => [{ stop: () => stopped++ }] });
    await starting;
    assert.equal(stopped, 1);
    assert.equal(state('cameraActive'), false);
});

test('timed out request reports an actionable error', async () => {
    const { context, timers } = harness();
    context.fetch = (_, options) =>
        new Promise((_, reject) =>
            options.signal.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError'))
            )
        );
    const request = context.apiRequest('/api/attendance');
    timers.values().next().value();
    await assert.rejects(request, /zaman aşımına uğradı/);
});

test('reset cancellation makes no request and focuses the safe action', async () => {
    const { context, ids, document, state } = harness();
    let requests = 0;
    context.fetch = async () => {
        requests++;
        throw new Error('Unexpected request');
    };
    state('attendanceLoaded = true;');
    context.updateAttendanceUI([{ id: '1', name: 'Ali', status: 'present' }]);
    const pending = context.resetAttendance();
    assert.equal(ids.get('reset-dialog').open, true);
    assert.equal(document.activeElement, ids.get('btn-reset-cancel'));
    ids.get('reset-dialog').close('cancel');
    await pending;
    assert.equal(requests, 0);
    assert.equal(state('studentsCache[0].status'), 'present');
    assert.equal(state('resetConfirmationPending'), false);
});

test('Escape and clicking the backdrop dismiss reset without confirming', async () => {
    const { context, ids } = harness();
    const dialog = ids.get('reset-dialog');
    const escape = context.confirmReset();
    let prevented = false;
    dialog.listeners.cancel({
        preventDefault() {
            prevented = true;
        }
    });
    assert.equal(await escape, false);
    assert.equal(prevented, true);
    const backdrop = context.confirmReset();
    dialog.listeners.click({ target: dialog, clientX: -1, clientY: -1 });
    assert.equal(await backdrop, false);
});

test('reset confirms one JSON POST then reloads attendance; duplicate action is ignored', async () => {
    const { context, ids, state } = harness();
    const requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            json: async () =>
                url.endsWith('/reset')
                    ? { success: true }
                    : {
                          generation: 'new-session',
                          students: [{ id: '1', name: 'Ali', status: 'absent' }]
                      }
        };
    };
    state('attendanceLoaded = true;');
    context.updateAttendanceUI([{ id: '1', name: 'Ali', status: 'present' }]);
    const first = context.resetAttendance();
    await context.resetAttendance();
    assert.equal(ids.get('reset-dialog').modalCount, 1);
    ids.get('reset-dialog').close('confirm');
    await first;
    assert.deepEqual(
        requests.map((request) => request.url),
        ['/api/attendance/reset', '/api/attendance']
    );
    assert.equal(requests[0].options.method, 'POST');
    assert.equal(requests[0].options.body, '{}');
    assert.equal(requests[0].options.headers['X-CSRF-Token'], 'test-csrf');
    assert.equal(state('studentsCache[0].status'), 'absent');
    assert.equal(state('serverGeneration'), 'new-session');
});

test('photos only use the exact same-student controlled URL with safe alt and lazy loading', () => {
    const { context } = harness();
    for (const url of [
        'https://attacker.invalid/photo',
        '//attacker.invalid/photo',
        'javascript:alert(1)',
        'data:image/svg+xml,test',
        '/api/students/2/photo',
        '/api/students/1/photo?redirect=x',
        '/api/students/1/photo/../2'
    ]) {
        assert.equal(context.safePhotoUrl(url, '1'), '');
        const card = context.createStudentCard({
            id: '1',
            name: 'Ali',
            status: 'absent',
            photo_url: url
        });
        assert.equal(card.querySelectorAll('img').length, 0);
    }
    const name = '<img src=x onerror=alert(1)>';
    const card = context.createStudentCard({
        id: '001',
        name,
        status: 'absent',
        photo_url: '/api/students/001/photo'
    });
    assert.equal(card.parts.photo.src, '/api/students/001/photo');
    assert.equal(card.parts.photo.alt, `${name} portresi`);
    assert.equal(card.parts.photo.loading, 'lazy');
    assert.equal(card.parts.photo.decoding, 'async');
    assert.equal(card.querySelectorAll('img').length, 1);
});

test('photo failure falls back to initials and stale image events cannot hide them', () => {
    const { context } = harness();
    const student = {
        id: '1',
        name: 'Ali Demir',
        status: 'absent',
        photo_url: '/api/students/1/photo'
    };
    const card = context.createStudentCard(student),
        photo = card.parts.photo;
    photo.listeners.load();
    assert.equal(card.parts.initials.hidden, true);
    photo.listeners.error();
    assert.equal(card.parts.photo, null);
    assert.equal(card.parts.initials.hidden, false);
    assert.equal(card.parts.initials.textContent, 'AD');
    photo.listeners.load();
    assert.equal(card.parts.initials.hidden, false);
    context.updateStudentCard(card, student);
    assert.equal(card.querySelectorAll('img').length, 0);
});

test('manual mode allows local camera preview and never calls recognition', async () => {
    const { context, ids, state } = harness();
    let requests = 0,
        stopped = 0;
    context.fetch = async () => {
        requests++;
        throw new Error('Preview must stay local');
    };
    context.navigator.mediaDevices = {
        getUserMedia: async () => ({
            getTracks: () => [{ stop: () => stopped++, addEventListener() {} }]
        })
    };
    state(
        'health = {mode:"manual", demo:true, recognition:{available:false}}; attendanceLoaded = true;'
    );
    context.updateControls();
    assert.equal(ids.get('btn-camera').disabled, false);
    await context.startCamera();
    assert.equal(state('cameraActive'), true);
    assert.equal(ids.get('btn-camera').querySelector('span').textContent, 'Kamerayı Durdur');
    assert.match(ids.get('status-badge').textContent, /Önizleme/);
    await context.captureAndRecognize();
    assert.equal(requests, 0);
    assert.equal(state('recognitionTimer'), null);
    assert.equal(state('fpsInterval'), null);
    context.stopCamera(false);
    assert.equal(stopped, 1);
    assert.equal(state('cameraActive'), false);
    assert.equal(ids.get('video').srcObject, null);
});
