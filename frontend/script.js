// Initialize Lucide Icons
lucide.createIcons();

// Elements
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

// Clock
function updateDateTime() {
    const el = document.getElementById('datetime');
    if(el) {
        const now = new Date();
        el.textContent = now.toLocaleDateString('pt-BR', { 
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        }).replace(',', ' |');
    }
}
setInterval(updateDateTime, 1000);
updateDateTime();

// Toast
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let icon = 'info';
    if(type === 'success') icon = 'check-circle';
    if(type === 'error') icon = 'alert-triangle';
    
    toast.innerHTML = `
        <i data-lucide="${icon}"></i>
        <span>${message}</span>
    `;
    toastContainer.appendChild(toast);
    lucide.createIcons();
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Navigation
navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        navBtns.forEach(b => b.classList.remove('active'));
        views.forEach(v => v.classList.remove('active'));
        
        btn.classList.add('active');
        document.getElementById(btn.dataset.target).classList.add('active');
        
        if(btn.dataset.target === 'view-dashboard') fetchAnalyses();
        if(btn.dataset.target === 'view-services') loadServices();
    });
});

// File Upload Drag & Drop
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-active');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-active');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-active');
    if (e.dataTransfer.files.length) {
        handleFileSelect(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFileSelect(e.target.files[0]);
    }
});

function handleFileSelect(file) {
    // Validate Max 10MB
    if (file.size > 10 * 1024 * 1024) {
        showToast('O arquivo excede o limite de 10MB.', 'error');
        return;
    }
    
    // Valid mime types
    const validMimes = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];
    if (!validMimes.includes(file.type)) {
        showToast('Formato de arquivo não suportado.', 'error');
        return;
    }

    currentFile = file;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    previewFilename.textContent = file.name;
    previewSize.textContent = `${sizeMb} MB`;
    
    uploadZone.querySelector('.upload-content').classList.add('hidden');
    filePreview.classList.remove('hidden');
}

window.removeSelectedFile = () => {
    currentFile = null;
    fileInput.value = '';
    uploadZone.querySelector('.upload-content').classList.remove('hidden');
    filePreview.classList.add('hidden');
}

// Upload Submission
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
        const response = await fetch('/api/v1/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Falha no upload');

        const data = await response.json();
        showToast('Diagrama enviado com sucesso!', 'success');
        removeSelectedFile();
        
        // Switch to dashboard
        document.querySelector('[data-target="view-dashboard"]').click();

    } catch (err) {
        showToast(err.message || 'Erro ao comunicar com a API.', 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Dashboard Functions
async function fetchAnalyses() {
    const tbody = document.getElementById('analyses-table-body');
    const refreshBtn = document.getElementById('btn-refresh-dashboard');
    refreshBtn.innerHTML = '<i data-lucide="loader" class="animate-spin"></i>';
    lucide.createIcons();

    try {
        const res = await fetch('/api/v1/reports');
        if (!res.ok) throw new Error('Erro ao listar análises');
        const data = await res.json();
        
        // Update stats
        let done = 0, proc = 0, err = 0;
        
        tbody.innerHTML = '';
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="text-align:center;color:var(--text-muted);">Nenhuma análise encontrada.</td></tr>';
        } else {
            // Reverse so newest is top
            data.reverse().forEach(item => {
                const s = item.status || 'RECEIVED';
                if(s === 'DONE') done++;
                else if(s === 'ERROR') err++;
                else proc++;

                const tr = document.createElement('tr');
                const dt = item.created_at ? new Date(item.created_at).toLocaleString() : '-';
                const idShort = item.id ? item.id.substring(0,8) + '...' : '-';
                
                tr.innerHTML = `
                    <td style="font-family: monospace; color: var(--text-muted);">${idShort}</td>
                    <td>${item.filename || '-'}</td>
                    <td>${dt}</td>
                    <td><span class="badge ${s.toLowerCase()}">${s}</span></td>
                    <td>
                        ${s === 'DONE' ? `<button class="btn btn-sm" onclick="viewReport('${item.id}')">Ver Detalhes</button>` : `<span style="font-size:12px;color:#71717a">Aguardando...</span>`}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        document.getElementById('stat-total').textContent = data.length;
        document.getElementById('stat-done').textContent = done;
        document.getElementById('stat-processing').textContent = proc;
        document.getElementById('stat-error').textContent = err;

    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--brand-danger);">Erro ao carregar análises: ${error.message}</td></tr>`;
    } finally {
        refreshBtn.innerHTML = '<i data-lucide="refresh-cw"></i> Atualizar';
        lucide.createIcons();
    }
}

// Report Modal
window.viewReport = async (id) => {
    reportModal.classList.remove('hidden');
    const body = document.getElementById('report-modal-body');
    body.innerHTML = '<div style="text-align:center;padding:40px;"><i data-lucide="loader" class="animate-spin" style="width:32px;height:32px;color:var(--brand-primary);"></i></div>';
    lucide.createIcons();

    try {
        const res = await fetch(`/api/v1/reports/${id}`);
        if(!res.ok) throw new Error('Não foi possível carregar o relatório.');
        const data = await res.json();
        const r = (data.analysis && data.analysis.ai) ? data.analysis.ai : {};
        const rawText = (data.analysis && data.analysis.text) ? data.analysis.text : '';

        let componentsHtml = (r.components || []).map(c => `
            <div class="alert-card" style="background: rgba(255,255,255,0.05); border-left: 3px solid var(--brand-primary); padding: 12px; margin-bottom: 8px;">
                <strong style="color: white;">${c.name}</strong> <span style="color:var(--text-muted);font-size:12px;">(${c.type})</span>
                <div style="margin-top: 4px; font-size: 13px;">${c.description}</div>
            </div>
        `).join('');
        
        let risksHtml = (r.risks || []).map(risk => `
            <div class="alert-card" style="margin-bottom: 8px;">
                <i data-lucide="alert-circle" style="display:inline-block;vertical-align:bottom;width:18px;margin-right:8px;"></i>
                <strong style="text-transform: uppercase;">[${risk.severity}]</strong> ${risk.description}
                <div style="margin-top: 8px; color: var(--brand-success); font-size: 13px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px;">
                    <i data-lucide="check-circle" style="display:inline-block;vertical-align:bottom;width:14px;margin-right:4px;"></i>
                    <strong>Recomendação:</strong> ${risk.recommendation}
                </div>
            </div>
        `).join('');

        let summaryHtml = r.summary ? `<p style="line-height: 1.6; color: var(--text-muted); padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">${r.summary.replace(/\n/g, '<br>')}</p>` : '<span style="color:#71717a">Nenhum</span>';
        let rawOcrHtml = rawText ? `<div style="max-height: 150px; overflow-y: auto; background: #000; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 11px; color: #00ff00; white-space: pre-wrap;">${rawText}</div>` : '';

        body.innerHTML = `
            <div class="report-section">
                <h3 style="color:var(--brand-primary)"><i data-lucide="file-text"></i> Resumo da Análise</h3>
                <div>${summaryHtml}</div>
            </div>
            ${rawOcrHtml ? `
            <div class="report-section">
                <h3><i data-lucide="scan-text"></i> Texto Bruto Extraído (OCR PDF)</h3>
                <div>${rawOcrHtml}</div>
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
    } catch(err) {
        body.innerHTML = `<div style="color:var(--brand-danger);padding:24px;">${err.message}</div>`;
    }
}

window.closeReportModal = () => {
    reportModal.classList.add('hidden');
}

let currentRating = 0;
function initStars() {
    currentRating = 0;
    const stars = document.querySelectorAll('#star-rating i');
    stars.forEach(s => {
        s.addEventListener('click', () => {
            currentRating = parseInt(s.dataset.val);
            stars.forEach(st => {
                if(parseInt(st.dataset.val) <= currentRating) st.style.fill = '#eab308';
                else st.style.fill = 'transparent';
            });
        });
    });
}

window.submitFeedback = async (id) => {
    if(currentRating === 0) {
        showToast('Selecione uma nota em estrelas.', 'error');
        return;
    }
    const comment = document.getElementById('feedback-comment').value;

    try {
        const res = await fetch(`/api/v1/reports/${id}/feedback`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ rating: currentRating, comment: comment })
        });
        if(!res.ok) throw new Error('Falha ao enviar feedback');
        showToast('Feedback enviado com sucesso!', 'success');
        closeReportModal();
    } catch(err) {
        showToast(err.message, 'error');
    }
}

// Services Check
const servicesCategories = [
    {
        title: 'Microsserviços',
        icon: 'cpu',
        items: [
            { name: 'Upload Service', desc: 'API responsável por receber e validar os arquivos submetidos.', port: 8001, url: 'http://localhost:8001/docs', color: '#009688', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/fastapi/fastapi-original.svg' },
            { name: 'AI Service', desc: 'Realiza orquestração das chamadas ao modelo (OpenAI) para extrair conclusões de arquitetura.', port: 8003, url: 'http://localhost:8003/docs', color: '#3776AB', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg' },
            { name: 'Report Service', desc: 'Consolida as respostas do banco de dados para formar relatórios.', port: 8004, url: 'http://localhost:8004/docs', color: '#009688', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/fastapi/fastapi-original.svg' }
        ]
    },
    {
        title: 'Dados e Mensageria',
        icon: 'database',
        items: [
            { name: 'RabbitMQ', desc: 'Broker de mensageria para a fila assíncrona de uploads.', port: 15672, url: 'http://localhost:15672', color: '#FF6600', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/rabbitmq/rabbitmq-original.svg' },
            { name: 'PostgreSQL', desc: 'Banco de dados relacional principal preservado.', port: 5432, url: '', color: '#336791', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/postgresql/postgresql-original.svg' }
        ]
    },
    {
        title: 'Monitoramento Observability',
        icon: 'activity',
        items: [
            { name: 'Grafana', desc: 'Dashboard avançado de monitoramento e logs visuais da infra.', port: 3000, url: 'http://localhost:3000', color: '#F46800', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/grafana/grafana-original.svg' },
            { name: 'Prometheus', desc: 'Motor de coleta e processamento de tempo métricas e logs.', port: 9090, url: 'http://localhost:9090', color: '#E6522C', imgUrl: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/prometheus/prometheus-original.svg' }
        ]
    }
];

async function loadServices() {
    const container = document.getElementById('services-container');
    container.innerHTML = '<div style="color:var(--text-muted);width:100%;text-align:center;">Consultando serviços...</div>';
    
    let html = '';
    
    for (const group of servicesCategories) {
        html += `
            <div style="margin-bottom: 32px; width: 100%;">
                <h3 style="font-size: 15px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; color: var(--text-muted); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i data-lucide="${group.icon}" style="width: 18px; height: 18px; color: var(--brand-primary);"></i>
                    ${group.title}
                </h3>
                <div class="services-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
        `;
        
        for (const s of group.items) {
            let isOnline = false;
            
            // O Browser não consegue fazer um 'ping' via HTTP Fetch no Postgres (porta TCP bruta). 
            // Portanto consultaremos o Report Service para verificar se o banco de dados está respondendo.
            if (s.name === 'PostgreSQL') {
                try {
                    const controller = new AbortController();
                    const id = setTimeout(() => controller.abort(), 2000);
                    const res = await fetch(`http://localhost:8004/health/db`, { signal: controller.signal });
                    clearTimeout(id);
                    isOnline = res.ok;
                } catch(e) {
                    isOnline = false;
                }
            } else {
                try {
                    const controller = new AbortController();
                    const id = setTimeout(() => controller.abort(), 1000);
                    await fetch(`http://localhost:${s.port}`, { mode: 'no-cors', signal: controller.signal });
                    clearTimeout(id);
                    isOnline = true;
                } catch(e) {
                    isOnline = false;
                }
            }

            const iconHtml = s.imgUrl 
                ? `<img src="${s.imgUrl}" alt="${s.name}" style="width:24px;height:24px;object-fit:contain;">`
                : `<i data-lucide="${s.icon}"></i>`;
                
            const linkBtn = s.url ? `<a href="${s.url}" target="_blank" class="btn btn-sm" style="margin-top: 8px;"><i data-lucide="external-link" style="width:14px;height:14px;margin-right:4px;"></i> Acessar</a>` : '';

            html += `
                <div class="service-card" style="--accent-color: ${s.color}; align-items: start;" data-desc="${s.desc}">
                    <div class="icon" style="background: rgba(255,255,255,0.1);">${iconHtml}</div>
                    <div class="info">
                        <div class="name">${s.name}</div>
                        <div class="desc">Porta :${s.port}</div>
                        ${linkBtn}
                    </div>
                    <div>
                        <span class="badge ${isOnline ? 'done' : 'error'}">
                            <span style="width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block;margin-right:2px;"></span>
                            ${isOnline ? 'On' : 'Off'}
                        </span>
                    </div>
                </div>
            `;
        }
        
        html += `
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
    lucide.createIcons();
}

// Initial Call
fetchAnalyses();
setInterval(() => {
    if(document.getElementById('view-dashboard').classList.contains('active')) {
        fetchAnalyses();
    }
}, 10000); // Polling every 10s
