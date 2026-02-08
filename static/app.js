// SD Prompt Batch Editor - Frontend

const state = {
    images: [],       // { id, filename, thumbnail, metadata }
    forgeConnected: false,
    generating: false,
    eventSource: null,
};

// --- Utility ---

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function showToast(message, type = 'info') {
    const container = $('.toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// --- Tokenizer (mirrors prompt_editor.py) ---

function tokenize(prompt) {
    const tokens = [];
    let current = [];
    let depthRound = 0, depthSquare = 0, depthAngle = 0;

    for (const ch of prompt) {
        if (ch === '(') { depthRound++; current.push(ch); }
        else if (ch === ')') { depthRound = Math.max(0, depthRound - 1); current.push(ch); }
        else if (ch === '[') { depthSquare++; current.push(ch); }
        else if (ch === ']') { depthSquare = Math.max(0, depthSquare - 1); current.push(ch); }
        else if (ch === '<') { depthAngle++; current.push(ch); }
        else if (ch === '>') { depthAngle = Math.max(0, depthAngle - 1); current.push(ch); }
        else if ((ch === ',' || ch === '\n') && depthRound === 0 && depthSquare === 0 && depthAngle === 0) {
            const token = current.join('').trim();
            if (token) tokens.push(token);
            current = [];
        }
        else { current.push(ch); }
    }
    const last = current.join('').trim();
    if (last) tokens.push(last);
    return tokens;
}

function extractCore(token) {
    let t = token.trim();
    if (t.startsWith('<') && t.endsWith('>')) return t;
    const re = /^[\(\[]+(.+?)(?::\s*[\d.]+)?[\)\]]+$/;
    let prev = null;
    while (t !== prev) {
        prev = t;
        const m = t.match(re);
        if (m) t = m[1].trim();
    }
    return t;
}

function removeTags(prompt, tagsToRemove) {
    if (!tagsToRemove.length) return prompt;
    const removeCores = new Set();
    for (const tag of tagsToRemove) {
        for (const sub of tokenize(tag)) {
            removeCores.add(extractCore(sub).toLowerCase());
        }
    }
    const tokens = tokenize(prompt);
    const filtered = tokens.filter(t => !removeCores.has(extractCore(t).toLowerCase()));
    return filtered.join(', ');
}

function addTags(prompt, tagsToAdd) {
    tagsToAdd = tagsToAdd.trim();
    if (!tagsToAdd) return prompt;
    prompt = prompt.trim();
    if (!prompt) return tagsToAdd;
    return prompt + ', ' + tagsToAdd;
}

function applyEdits(prompt, remove, add) {
    const removeList = remove.split(',').map(t => t.trim()).filter(Boolean);
    let result = removeTags(prompt, removeList);
    result = addTags(result, add);
    return result;
}

function findCommonTags(prompts) {
    if (!prompts.length) return [];
    const tagSets = prompts.map(p => {
        const cores = new Set();
        for (const token of tokenize(p)) cores.add(extractCore(token).toLowerCase());
        return cores;
    });
    let common = tagSets[0];
    for (let i = 1; i < tagSets.length; i++) {
        common = new Set([...common].filter(x => tagSets[i].has(x)));
    }
    const result = [];
    const seen = new Set();
    for (const token of tokenize(prompts[0])) {
        const core = extractCore(token).toLowerCase();
        if (common.has(core) && !seen.has(core)) {
            result.push(extractCore(token));
            seen.add(core);
        }
    }
    return result;
}

// --- Forge Connection ---

async function checkForge() {
    const host = $('#forge-host').value.trim();
    const port = $('#forge-port').value.trim();
    try {
        const resp = await fetch(`/api/check-forge?host=${encodeURIComponent(host)}&port=${encodeURIComponent(port)}`);
        const data = await resp.json();
        state.forgeConnected = data.connected;
    } catch {
        state.forgeConnected = false;
    }
    updateForgeStatus();
}

function updateForgeStatus() {
    const dot = $('.status-dot');
    const label = $('#forge-status-text');
    if (state.forgeConnected) {
        dot.classList.add('connected');
        label.textContent = '接続中';
    } else {
        dot.classList.remove('connected');
        label.textContent = '未接続';
    }
}

// --- Image Upload ---

async function uploadFiles(files) {
    for (const file of files) {
        if (file.type !== 'image/png') {
            showToast(`${file.name}: PNGファイルのみ対応`, 'error');
            continue;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const resp = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await resp.json();

            if (data.error) {
                showToast(`${file.name}: ${data.error}`, 'error');
                continue;
            }

            state.images.push({
                id: data.id,
                filename: data.filename,
                thumbnail: data.thumbnail,
                metadata: data.metadata,
            });
        } catch (e) {
            showToast(`${file.name}: アップロード失敗`, 'error');
        }
    }
    renderImages();
    renderCommonTags();
}

function removeImage(id) {
    state.images = state.images.filter(img => img.id !== id);
    renderImages();
    renderCommonTags();
}

function clearAllImages() {
    state.images = [];
    renderImages();
    renderCommonTags();
}

// --- Rendering ---

function renderImages() {
    const grid = $('.image-grid');
    const noImages = $('.no-images');
    const clearBtn = $('#clear-all-btn');

    if (state.images.length === 0) {
        grid.innerHTML = '';
        noImages.classList.remove('hidden');
        clearBtn.classList.add('hidden');
        return;
    }

    noImages.classList.add('hidden');
    clearBtn.classList.remove('hidden');

    grid.innerHTML = state.images.map(img => `
        <div class="image-card" data-id="${img.id}">
            <img src="${img.thumbnail}" alt="${img.filename}">
            <div class="filename" title="${img.filename}">${img.filename}</div>
            <button class="remove-btn" onclick="removeImage('${img.id}')">&times;</button>
        </div>
    `).join('');
}

function renderCommonTags() {
    const posContainer = $('#common-positive');
    const negContainer = $('#common-negative');

    if (state.images.length === 0) {
        posContainer.innerHTML = '<span class="no-images">画像を読み込んでください</span>';
        negContainer.innerHTML = '';
        return;
    }

    const positives = state.images.map(img => img.metadata.positive_prompt);
    const negatives = state.images.map(img => img.metadata.negative_prompt);

    const commonPos = findCommonTags(positives);
    const commonNeg = findCommonTags(negatives);

    posContainer.innerHTML = commonPos.length
        ? commonPos.map(t => `<span class="tag clickable" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join('')
        : '<span style="color:var(--text-secondary);font-size:0.85rem;">共通タグなし</span>';

    negContainer.innerHTML = commonNeg.length
        ? commonNeg.map(t => `<span class="tag clickable" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join('')
        : '<span style="color:var(--text-secondary);font-size:0.85rem;">共通タグなし</span>';

    // Add click-to-copy handlers
    for (const el of $$('.tag.clickable')) {
        el.addEventListener('click', () => {
            navigator.clipboard.writeText(el.dataset.tag).then(() => {
                showToast(`コピー: ${el.dataset.tag}`, 'info');
            });
        });
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// --- Preview ---

function showPreview() {
    const removePos = $('#edit-remove-pos').value;
    const removeNeg = $('#edit-remove-neg').value;
    const addPos = $('#edit-add-pos').value;
    const addNeg = $('#edit-add-neg').value;

    const previewList = $('.preview-list');
    const previewSection = $('#preview-section');
    previewSection.classList.remove('hidden');

    if (state.images.length === 0) {
        previewList.innerHTML = '<p class="no-images">画像がありません</p>';
        return;
    }

    previewList.innerHTML = state.images.map(img => {
        const newPos = applyEdits(img.metadata.positive_prompt, removePos, addPos);
        const newNeg = applyEdits(img.metadata.negative_prompt, removeNeg, addNeg);

        return `
            <div class="preview-item">
                <div class="preview-filename">${escapeHtml(img.filename)}</div>
                <div class="preview-label">Positive:</div>
                <div class="preview-text">${escapeHtml(newPos)}</div>
                <div class="preview-label">Negative:</div>
                <div class="preview-text">${escapeHtml(newNeg)}</div>
            </div>
        `;
    }).join('');
}

// --- Generation ---

async function startGeneration() {
    if (state.images.length === 0) {
        showToast('画像を読み込んでください', 'error');
        return;
    }

    if (state.generating) return;

    const host = $('#forge-host').value.trim();
    const port = $('#forge-port').value.trim();
    const removePos = $('#edit-remove-pos').value;
    const removeNeg = $('#edit-remove-neg').value;
    const addPos = $('#edit-add-pos').value;
    const addNeg = $('#edit-add-neg').value;

    if (!removePos && !removeNeg && !addPos && !addNeg) {
        showToast('編集内容を入力してください', 'error');
        return;
    }

    state.generating = true;
    $('#btn-generate').disabled = true;

    // Show progress section
    const progressSection = $('.progress-section');
    progressSection.classList.add('active');
    $('.progress-bar').style.width = '0%';
    $('.progress-bar').textContent = '0%';
    $('.progress-status').textContent = '生成開始中...';
    $('.progress-log').innerHTML = '';

    try {
        const resp = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                host,
                port,
                images: state.images.map(img => ({
                    id: img.id,
                    filename: img.filename,
                    metadata: img.metadata,
                })),
                edits: {
                    remove_positive: removePos,
                    remove_negative: removeNeg,
                    add_positive: addPos,
                    add_negative: addNeg,
                },
            }),
        });

        const data = await resp.json();
        if (data.error) {
            showToast(data.error, 'error');
            state.generating = false;
            $('#btn-generate').disabled = false;
            return;
        }

        // Connect SSE for progress
        connectSSE(data.session_id);
    } catch (e) {
        showToast('生成リクエスト失敗', 'error');
        state.generating = false;
        $('#btn-generate').disabled = false;
    }
}

function connectSSE(sessionId) {
    if (state.eventSource) {
        state.eventSource.close();
    }

    const es = new EventSource(`/api/generate/progress?session_id=${sessionId}`);
    state.eventSource = es;

    es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        const pct = Math.round((data.current / data.total) * 100);
        $('.progress-bar').style.width = pct + '%';
        $('.progress-bar').textContent = pct + '%';
        $('.progress-status').textContent = `生成中: ${data.current}/${data.total} - ${data.filename}`;
    });

    es.addEventListener('image_done', (e) => {
        const data = JSON.parse(e.data);
        addLogEntry(`${data.filename} - 完了`, 'success');
    });

    es.addEventListener('error_event', (e) => {
        const data = JSON.parse(e.data);
        addLogEntry(`${data.filename} - エラー: ${data.message}`, 'error');
    });

    es.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        state.eventSource = null;
        state.generating = false;
        $('#btn-generate').disabled = false;

        $('.progress-bar').style.width = '100%';
        $('.progress-bar').textContent = '100%';
        $('.progress-status').textContent = `完了! 出力: ${data.output_dir}`;

        addLogEntry(`全${data.total}枚の生成が完了 (成功: ${data.success}, 失敗: ${data.failed})`, 'success');
        showToast(`生成完了: ${data.success}枚成功`, 'success');

        // Browser notification
        if (Notification.permission === 'granted') {
            new Notification('SD Prompt Batch Editor', {
                body: `生成完了: ${data.success}枚成功`,
            });
        }
    });

    es.onerror = () => {
        es.close();
        state.eventSource = null;
        if (state.generating) {
            state.generating = false;
            $('#btn-generate').disabled = false;
            showToast('SSE接続が切断されました', 'error');
        }
    };
}

function addLogEntry(text, type = '') {
    const log = $('.progress-log');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = text;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    // Drop zone
    const dropZone = $('.drop-zone');

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        uploadFiles(e.dataTransfer.files);
    });

    dropZone.addEventListener('click', () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/png';
        input.multiple = true;
        input.onchange = () => uploadFiles(input.files);
        input.click();
    });

    // Buttons
    $('#clear-all-btn').addEventListener('click', clearAllImages);
    $('#btn-preview').addEventListener('click', showPreview);
    $('#btn-generate').addEventListener('click', startGeneration);

    // Forge connection check
    checkForge();
    setInterval(checkForge, 30000);

    // Notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    renderImages();
    renderCommonTags();
});
