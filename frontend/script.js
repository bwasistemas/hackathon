/* global lucide */
// security-logger.js is loaded as a classic script and exposes window.securityLogger.
// We resolve it through `window` and fall back to a no-op so a missing/blocked
// security-logger.js never breaks the login flow.
const securityLogger = (typeof window !== 'undefined' && window.securityLogger) || {
    info() {}, warn() {}, error() {},
    authAttempt() {}, rateLimitExceeded() {}, suspiciousActivity() {},
};

lucide.createIcons();

const TOKEN_STORAGE_KEY = 'authToken';

function getToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
}

function setToken(token) {
    if (token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
}

let authToken = getToken();

const loginScreen = document.getElementById('login-screen');
const appContainer = document.getElementById('app-container');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const logoutBtn = document.getElementById('logout-btn');

const navBtns = document.querySelectorAll('.nav-btn');
const views = document.querySelectorAll('.view-section');
const fileInput = document.getElementById('file-input');
const uploadZone = document.getElementById('upload-zone');
const filePreview = document.getElementById('file-preview');
const previewFilename = document.getElementById('preview-filename');
const previewSize = document.getElementById('preview-size');
const toastContainer = document.getElementById('toast-container');
const reportModal = document.getElementById('report-modal');

let currentFile = null;
let pollingHandle = null;

// ---------- Helpers ----------

/**
 * Escape any value before rendering it into innerHTML to prevent XSS.
 * Filenames, OCR text, AI summaries and component descriptions all flow
 * back into the dashboard – they MUST never be trusted.
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Wraps fetch() with the bearer token and centralised handling of 401
 * (token expired / invalid) responses, which force a logout.
 */
async function apiFetch(input, init = {}) {
    const headers = new Headers(init.headers || {});
    if (authToken && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${authToken}`);
    }
    const response = await fetch(input, { ...init, headers });
    if (response.status === 401) {
        securityLogger.warn('Auth token rejected, forcing logout', { url: typeof input === 'string' ? input : input.url });
        logout();
        throw new Error('Sessão expirada. Faça login novamente.');
    }
    return response;
}

if (authToken) {
    showApp();
} else {
    showLogin();
}

function showLogin() {
    loginScreen.style.display = 'flex';
    appContainer.style.display = 'none';
}

function showApp() {
    loginScreen.style.display = 'none';
    appContainer.style.display = 'flex';
    initializeApp();
}

function initializeApp() {
    if (initializeApp._initialized) {
        return; // protect against double-binding when login/logout cycles
    }
    initializeApp._initialized = true;

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.id === 'logout-btn') return;
            navBtns.forEach(b => b.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            btn.classList.add('active');
            const target = document.getElementById(btn.dataset.target);
            if (target) target.classList.add('active');
            if (btn.dataset.target === 'view-dashboard') fetchAnalyses();
            if (btn.dataset.target === 'view-services') loadServices();
        });
    });

    // Only open the file picker when clicking the empty drop area — not when
    // clicking buttons inside #file-preview ("Iniciar Análise") or other controls,
    // otherwise the click bubbles here and re-opens the upload dialog.
    uploadZone.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        if (e.target.closest('#file-preview')) return;
        const content = uploadZone.querySelector('.upload-content');
        if (content && !content.classList.contains('hidden')) {
            fileInput.click();
        }
    });
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-active'));
    uploadZone.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFileSelect(e.target.files[0]);
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') reportModal.classList.add('hidden');
    });

    const btnRefreshDashboard = document.getElementById('btn-refresh-dashboard');
    if (btnRefreshDashboard) {
        btnRefreshDashboard.addEventListener('click', () => fetchAnalyses());
    }
    const btnSelectFile = document.getElementById('btn-select-file');
    if (btnSelectFile) {
        btnSelectFile.addEventListener('click', () => fileInput.click());
    }
    const btnRemoveFile = document.getElementById('btn-remove-file');
    if (btnRemoveFile) {
        btnRemoveFile.addEventListener('click', () => window.removeSelectedFile());
    }
    const btnSubmitUpload = document.getElementById('btn-submit-upload');
    if (btnSubmitUpload) {
        btnSubmitUpload.addEventListener('click', (e) => {
            e.stopPropagation();
            window.submitUpload();
        });
    }
    const reportModalBackdrop = document.getElementById('report-modal-backdrop');
    if (reportModalBackdrop) {
        reportModalBackdrop.addEventListener('click', () => window.closeReportModal());
    }
    const btnCloseReportModal = document.getElementById('btn-close-report-modal');
    if (btnCloseReportModal) {
        btnCloseReportModal.addEventListener('click', () => window.closeReportModal());
    }

    fetchAnalyses();
    if (pollingHandle) clearInterval(pollingHandle);
    pollingHandle = setInterval(() => {
        if (document.getElementById('view-dashboard').classList.contains('active')) {
            fetchAnalyses();
        }
    }, 10000);
}

// ---------- Auth ----------

async function login(username, password) {
    try {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch('/upload-service/token', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            securityLogger.authAttempt(false, username);
            const detail = response.status === 429
                ? 'Muitas tentativas. Aguarde alguns segundos e tente novamente.'
                : 'Credenciais inválidas';
            throw new Error(detail);
        }

        const data = await response.json();
        authToken = data.access_token;
        setToken(authToken);
        securityLogger.authAttempt(true, username);
        loginError.style.display = 'none';
        showApp();
    } catch (error) {
        loginError.textContent = error.message;
        loginError.style.display = 'block';
        securityLogger.error('Login failed', { error: error.message });
    }
}

function logout() {
    authToken = null;
    setToken(null);
    if (pollingHandle) {
        clearInterval(pollingHandle);
        pollingHandle = null;
    }
    initializeApp._initialized = false;
    showLogin();
}

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(loginForm);
    await login(formData.get('username'), formData.get('password'));
});

logoutBtn.addEventListener('click', logout);

// ---------- Clock ----------

function updateDateTime() {
    const el = document.getElementById('datetime');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleDateString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    }).replace(',', ' |');
}
setInterval(updateDateTime, 1000);
updateDateTime();

// ---------- Toast ----------

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let icon = 'info';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'alert-triangle';

    const iconEl = document.createElement('i');
    iconEl.setAttribute('data-lucide', icon);
    const span = document.createElement('span');
    span.textContent = message; // textContent prevents XSS
    toast.appendChild(iconEl);
    toast.appendChild(span);
    toastContainer.appendChild(toast);
    lucide.createIcons();

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ---------- File Upload ----------

function handleDragOver(e) {
    e.preventDefault();
    uploadZone.classList.add('drag-active');
}

function handleDrop(e) {
    e.preventDefault();
    uploadZone.classList.remove('drag-active');
    if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
}

function handleFileSelect(file) {
    if (file.size > 10 * 1024 * 1024) {
        showToast('O arquivo excede o limite de 10MB.', 'error');
        return;
    }
    const validMimes = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];
    if (!validMimes.includes(file.type)) {
        showToast('Formato de arquivo não suportado.', 'error');
        return;
    }

    currentFile = file;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    previewFilename.textContent = file.name; // textContent: safe
    previewSize.textContent = `${sizeMb} MB`;
    uploadZone.querySelector('.upload-content').classList.add('hidden');
    filePreview.classList.remove('hidden');
}

window.removeSelectedFile = () => {
    currentFile = null;
    fileInput.value = '';
    uploadZone.querySelector('.upload-content').classList.remove('hidden');
    filePreview.classList.add('hidden');
};

window.submitUpload = async () => {
    if (!currentFile) return;

    const btn = document.getElementById('btn-submit-upload');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i data-lucide="loader" class="animate-spin"></i> Enviando...';
    btn.disabled = true;
    lucide.createIcons();

    const formData = new FormData();
    formData.append('file', currentFile);

    try {
        const response = await apiFetch('/upload-service/upload', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            securityLogger.warn('Upload failed', {
                status: response.status,
                size: currentFile.size,
            });
            throw new Error('Falha no upload');
        }

        const data = await response.json();
        securityLogger.info('Upload successful', { size: currentFile.size, uploadId: data.id });
        showToast('Diagrama enviado com sucesso!', 'success');
        window.removeSelectedFile();
        document.querySelector('[data-target="view-dashboard"]').click();
    } catch (err) {
        securityLogger.error('Upload error', { error: err.message });
        showToast(err.message || 'Erro ao comunicar com a API.', 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
};

// ---------- Dashboard ----------

async function fetchAnalyses() {
    const tbody = document.getElementById('analyses-table-body');
    const refreshBtn = document.getElementById('btn-refresh-dashboard');
    refreshBtn.innerHTML = '<i data-lucide="loader" class="animate-spin"></i>';
    lucide.createIcons();

    try {
        const res = await apiFetch('/report-service/reports');
        if (!res.ok) throw new Error('Erro ao listar análises');
        const data = await res.json();

        let done = 0, proc = 0, err = 0;
        tbody.innerHTML = '';
        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="text-align:center;color:var(--text-muted);">Nenhuma análise encontrada.</td></tr>';
        } else {
            data.reverse().forEach(item => {
                const s = item.status || 'RECEIVED';
                if (s === 'DONE') done++;
                else if (s === 'ERROR') err++;
                else proc++;

                const tr = document.createElement('tr');
                const dt = item.created_at ? new Date(item.created_at).toLocaleString() : '-';
                const idShort = item.id ? String(item.id).substring(0, 8) + '...' : '-';
                const safeId = escapeHtml(item.id || '');
                const safeFilename = escapeHtml(item.filename || '-');
                const safeStatus = escapeHtml(s);

                tr.innerHTML = `
                    <td style="font-family: monospace; color: var(--text-muted);">${escapeHtml(idShort)}</td>
                    <td>${safeFilename}</td>
                    <td>${escapeHtml(dt)}</td>
                    <td><span class="badge ${safeStatus.toLowerCase()}">${safeStatus}</span></td>
                    <td>
                        ${s === 'DONE'
                            ? `<button class="btn btn-sm" data-action="view-report" data-id="${safeId}">Ver Detalhes</button>`
                            : `<span style="font-size:12px;color:#71717a">Aguardando...</span>`}
                    </td>
                `;
                tbody.appendChild(tr);
            });

            tbody.querySelectorAll('button[data-action="view-report"]').forEach(btn => {
                btn.addEventListener('click', () => window.viewReport(btn.dataset.id));
            });
        }

        document.getElementById('stat-total').textContent = data.length;
        document.getElementById('stat-done').textContent = done;
        document.getElementById('stat-processing').textContent = proc;
        document.getElementById('stat-error').textContent = err;
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--brand-danger);">${escapeHtml('Erro ao carregar análises: ' + error.message)}</td></tr>`;
    } finally {
        refreshBtn.innerHTML = '<i data-lucide="refresh-cw"></i> Atualizar';
        lucide.createIcons();
    }
}
window.fetchAnalyses = fetchAnalyses;

// ---------- Report Modal ----------

window.viewReport = async (id) => {
    reportModal.classList.remove('hidden');
    const body = document.getElementById('report-modal-body');
    body.innerHTML = '<div style="text-align:center;padding:40px;"><i data-lucide="loader" class="animate-spin" style="width:32px;height:32px;color:var(--brand-primary);"></i></div>';
    lucide.createIcons();

    try {
        const res = await apiFetch(`/report-service/reports/${encodeURIComponent(id)}`);
        if (!res.ok) throw new Error('Não foi possível carregar o relatório.');
        const data = await res.json();
        const analysisRoot = data.analysis || {};
        const r = analysisRoot.ai || {};
        const rawText = analysisRoot.text || '';

        const errMsg = r.error ? String(r.error) : '';
        const errorBanner = errMsg
            ? `<div class="alert-card" style="border-left:3px solid var(--brand-danger);margin-bottom:16px;">
                   <strong>Erro na análise LLM / OCR</strong>
                   <div style="margin-top:8px;font-size:13px;">${escapeHtml(errMsg)}</div>
               </div>`
            : '';
        const componentsHtml = (r.components || []).map(c => `
            <div class="alert-card" style="background: rgba(255,255,255,0.05); border-left: 3px solid var(--brand-primary); padding: 12px; margin-bottom: 8px;">
                <strong style="color: white;">${escapeHtml(c.name)}</strong>
                <span style="color:var(--text-muted);font-size:12px;">(${escapeHtml(c.type)})</span>
                <div style="margin-top: 4px; font-size: 13px;">${escapeHtml(c.description)}</div>
            </div>
        `).join('');

        const recFallback =
            '<span style="color:#71717a;font-style:italic;">Nenhuma recomendação específica foi retornada pelo modelo para este risco.</span>';
        const risksHtml = (r.risks || []).map(risk => {
            const rec = risk.recommendation && String(risk.recommendation).trim();
            const recBlock = rec
                ? escapeHtml(rec)
                : recFallback;
            return `
            <div class="alert-card" style="margin-bottom: 8px;">
                <i data-lucide="alert-circle" style="display:inline-block;vertical-align:bottom;width:18px;margin-right:8px;"></i>
                <strong style="text-transform: uppercase;">[${escapeHtml(risk.severity)}]</strong> ${escapeHtml(risk.description)}
                <div style="margin-top: 8px; color: var(--brand-success); font-size: 13px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px;">
                    <i data-lucide="check-circle" style="display:inline-block;vertical-align:bottom;width:14px;margin-right:4px;"></i>
                    <strong>Recomendação:</strong> ${recBlock}
                </div>
            </div>
        `;
        }).join('');

        const safeSummary = r.summary
            ? `<p style="line-height: 1.6; color: var(--text-muted); padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">${escapeHtml(r.summary).replace(/\n/g, '<br>')}</p>`
            : '<span style="color:#71717a">Nenhum</span>';

        const sourceAssessment =
            r.source_assessment ||
            r.avaliacao_fonte ||
            r['avaliação_fonte'] ||
            r.interpretacao_entrada ||
            r['interpretação_entrada'] ||
            '';
        const safeSourceAssessment = sourceAssessment
            ? `<p style="line-height: 1.6; color: var(--text-muted); padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">${escapeHtml(String(sourceAssessment)).replace(/\n/g, '<br>')}</p>`
            : '<span style="color:#71717a">Nenhuma avaliação da entrada foi devolvida pelo modelo (analises antigas ou resposta sem o campo).</span>';

        const tex = analysisRoot.text_extraction;
        const texSource = tex && tex.source;
        const texDetail = tex && tex.detail_pt;
        const texModel = tex && tex.multimodal_model;

        let extractionMetaHtml = '';
        if (texDetail) {
            const isLlm = texSource === 'llm_multimodal';
            const badgeLabel = isLlm ? 'Modelo multimodal (LLM_OCR)' : 'OCR Tesseract (local / fallback)';
            const badgeColor = isLlm ? 'var(--brand-primary)' : '#ca8a04';
            extractionMetaHtml = `
            <div class="alert-card" style="margin-bottom:12px;border-left:4px solid ${badgeColor};background:rgba(255,255,255,0.06);padding:12px;">
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="font-size:11px;text-transform:uppercase;font-weight:700;color:${badgeColor};letter-spacing:0.03em;">${escapeHtml(badgeLabel)}</span>
                    ${texModel ? `<span style="font-size:12px;color:var(--text-muted);font-family:monospace;">${escapeHtml(texModel)}</span>` : ''}
                </div>
                <p style="margin:0;font-size:13px;line-height:1.55;color:var(--text-muted);">${escapeHtml(texDetail)}</p>
            </div>`;
        } else if (rawText) {
            extractionMetaHtml = `
            <div class="alert-card" style="margin-bottom:12px;border-left:3px solid #71717a;background:rgba(255,255,255,0.04);padding:12px;">
                <p style="margin:0;font-size:13px;color:var(--text-muted);">Fonte da extração não registada (relatório anterior à atualização do sistema).</p>
            </div>`;
        }

        const pipelineSubtitle =
            texSource === 'llm_multimodal'
                ? 'O bloco abaixo foi gerado pelo modelo multimodal (env <code style="font-size:11px;">LLM_OCR</code>) ao analisar a imagem ou o PDF — não é saída do Tesseract.'
                : texSource === 'tesseract'
                  ? 'O bloco abaixo veio do OCR local (Tesseract). Se houve tentativa de LLM multimodal, ela falhou ou está desativada — ver o quadro acima.'
                  : 'Conteúdo bruto usado como entrada para a análise arquitetural (extração ou relatório legado).';

        const rawOcrHtml = rawText
            ? `<div style="max-height: 150px; overflow-y: auto; background: #000; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 11px; color: #00ff00; white-space: pre-wrap;">${escapeHtml(rawText)}</div>`
            : '';

        const pipelineSectionVisible = rawText || extractionMetaHtml;

        body.innerHTML = `
            ${errorBanner}
            <div class="report-section">
                <h3 style="color:var(--brand-primary)"><i data-lucide="file-text"></i> Resumo da Análise</h3>
                <div>${safeSummary}</div>
            </div>
            <div class="report-section">
                <h3><i data-lucide="sparkles"></i> Como a IA interpretou o OCR</h3>
                <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px 0;">Texto escrito pelo modelo sobre limitações do OCR e suposições — não é o texto bruto do ficheiro.</p>
                <div>${safeSourceAssessment}</div>
            </div>
            ${pipelineSectionVisible ? `
            <div class="report-section">
                <h3><i data-lucide="scan-text"></i> Texto bruto do pipeline (OCR / extração)</h3>
                <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px 0;line-height:1.45;">${pipelineSubtitle}</p>
                ${extractionMetaHtml}
                ${rawOcrHtml || '<span style="color:#71717a;font-size:13px;">Nenhum texto bruto foi guardado para este envio.</span>'}
            </div>
            ` : ''}
            <div class="report-section">
                <h3><i data-lucide="box"></i> Componentes Identificados</h3>
                <div>${componentsHtml || '<span style="color:#71717a">Nenhum</span>'}</div>
            </div>
            <div class="report-section">
                <h3 style="color:var(--brand-danger)"><i data-lucide="alert-triangle"></i> Riscos Arquiteturais</h3>
                <div>${risksHtml || '<span style="color:#71717a">Nenhum</span>'}</div>
            </div>
        `;
        lucide.createIcons();
        initStars();
    } catch (err) {
        body.innerHTML = `<div style="color:var(--brand-danger);padding:24px;">${escapeHtml(err.message)}</div>`;
    }
};

window.closeReportModal = () => {
    reportModal.classList.add('hidden');
};

let currentRating = 0;
function initStars() {
    currentRating = 0;
    const stars = document.querySelectorAll('#star-rating i');
    stars.forEach(s => {
        s.addEventListener('click', () => {
            currentRating = parseInt(s.dataset.val, 10);
            stars.forEach(st => {
                if (parseInt(st.dataset.val, 10) <= currentRating) st.style.fill = '#eab308';
                else st.style.fill = 'transparent';
            });
        });
    });
}

window.submitFeedback = async (id) => {
    if (currentRating === 0) {
        showToast('Selecione uma nota em estrelas.', 'error');
        return;
    }
    const comment = document.getElementById('feedback-comment').value;

    try {
        const res = await apiFetch('/report-service/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ upload_id: id, rating: currentRating, comment }),
        });
        if (!res.ok) throw new Error('Falha ao enviar feedback');
        showToast('Feedback enviado com sucesso!', 'success');
        window.closeReportModal();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

// ---------- Services Status ----------

const servicesCategories = [
    {
        title: 'Microsserviços',
        icon: 'cpu',
        items: [
            { name: 'Upload Service', desc: 'API responsável por receber e validar os arquivos submetidos.', port: 8001, healthPath: '/upload-service/health' },
            { name: 'AI Service', desc: 'Realiza orquestração das chamadas ao modelo (OpenAI) para extrair conclusões de arquitetura.', port: 8003, healthPath: '/ai-service/health' },
            { name: 'Report Service', desc: 'Consolida as respostas do banco de dados para formar relatórios.', port: 8004, healthPath: '/report-service/health' },
        ],
    },
    {
        title: 'Dados e Mensageria',
        icon: 'database',
        items: [
            {
                name: 'RabbitMQ',
                desc: 'Broker de mensageria para a fila assíncrona de uploads.',
                port: 15672,
                healthPath: '/infra-health/rabbitmq',
                externalUrl: 'http://localhost:15672',
            },
            {
                name: 'PostgreSQL',
                desc: 'Banco de dados relacional principal.',
                port: 5432,
                healthPath: '/report-service/health/db',
            },
        ],
    },
    {
        title: 'Monitoramento',
        icon: 'activity',
        items: [
            {
                name: 'Grafana',
                desc: 'Dashboard avançado de monitoramento.',
                port: 3000,
                healthPath: '/infra-health/grafana',
                externalUrl: 'http://localhost:3000',
            },
            {
                name: 'Prometheus',
                desc: 'Motor de coleta de métricas.',
                port: 9090,
                healthPath: '/infra-health/prometheus',
                externalUrl: 'http://localhost:9090',
            },
        ],
    },
];

async function probe(url) {
    try {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), 2000);
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(id);
        return res.ok;
    } catch {
        return false;
    }
}

async function loadServices() {
    const container = document.getElementById('services-container');
    container.innerHTML = '<div style="color:var(--text-muted);width:100%;text-align:center;">Consultando serviços...</div>';

    const fragments = [];
    for (const group of servicesCategories) {
        const cards = [];
        for (const s of group.items) {
            let isOnline = false;
            if (s.healthPath) {
                isOnline = await probe(s.healthPath);
            } else if (s.externalUrl) {
                isOnline = await probe(s.externalUrl);
            }
            const linkBtn = s.externalUrl
                ? `<a href="${escapeHtml(s.externalUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm" style="margin-top: 8px;"><i data-lucide="external-link" style="width:14px;height:14px;margin-right:4px;"></i> Acessar</a>`
                : '';
            cards.push(`
                <div class="service-card" style="align-items: start;">
                    <div class="info">
                        <div class="name">${escapeHtml(s.name)}</div>
                        <div class="desc">Porta :${escapeHtml(s.port)}</div>
                        ${linkBtn}
                    </div>
                    <div>
                        <span class="badge ${isOnline ? 'done' : 'error'}">
                            <span style="width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block;margin-right:2px;"></span>
                            ${isOnline ? 'On' : 'Off'}
                        </span>
                    </div>
                </div>
            `);
        }
        fragments.push(`
            <div style="margin-bottom: 32px; width: 100%;">
                <h3 style="font-size: 15px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; color: var(--text-muted); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i data-lucide="${escapeHtml(group.icon)}" style="width: 18px; height: 18px; color: var(--brand-primary);"></i>
                    ${escapeHtml(group.title)}
                </h3>
                <div class="services-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                    ${cards.join('')}
                </div>
            </div>
        `);
    }
    container.innerHTML = fragments.join('');
    lucide.createIcons();
}
window.loadServices = loadServices;
