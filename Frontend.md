Você é um engenheiro sênior especializado em Frontend Web Moderno (Vanilla JS, HTML e CSS).

## CONTEXTO

Estou construindo um MVP de análise automatizada de diagramas de arquitetura de software (hackathon acadêmico). O backend são microsserviços Python/FastAPI com RabbitMQ. Preciso de um frontend SPA (Single Page Application) em Vanilla HTML/CSS/JS (sem frameworks grandes como React para simplicidade, apenas servido via Nginx na porta 8051) que cubra 3 telas/seções na Central de Comando:

1. **Upload** — enviar diagrama e disparar a análise
2. **Dashboard** — acompanhar status de todas as análises em tempo real
3. **Relatório + Feedback** — visualizar o relatório gerado e dar feedback

### APIs disponíveis no backend:
```
# Upload Service (porta 8001)
POST   /api/v1/upload                 → multipart/form-data (campo: file)
                                        Retorna: { "analysis_id": "uuid", "status": "RECEIVED", "filename": "...", "created_at": "..." }

GET    /api/v1/analysis/{id}/status   → Retorna: { "analysis_id": "uuid", "status": "RECEIVED|PROCESSING|DONE|ERROR", "updated_at": "..." }

# Report Service (porta 8004)  
GET    /api/v1/reports/{analysis_id}  → Retorna relatório completo:
                                        {
                                          "analysis_id": "uuid",
                                          "filename": "...",
                                          "status": "DONE",
                                          "result": {
                                            "components": ["API Gateway", "Database", ...],
                                            "risks": ["Single point of failure", ...],
                                            "recommendations": ["Add load balancer", ...]
                                          },
                                          "created_at": "...",
                                          "completed_at": "..."
                                        }

GET    /api/v1/reports                → Lista todas as análises: [{ analysis_id, filename, status, created_at }, ...]

POST   /api/v1/reports/{analysis_id}/feedback → Body: { "rating": 1-5, "comment": "texto" }
                                                Retorna: { "success": true }
```

## O QUE FOI GERADO

### 1. App Single Page (HTML/JS/CSS) no Nginx

Estrutura:
```
frontend/
├── index.html                # Entry point, config da navegação
├── styles.css                # Visual moderno, glassmorphism e Dark Theme
├── script.js                 # Lógica Vanilla JS de manipulação DOM e fetch APIs
├── nginx.conf                # Proxy reverso e server estático na 8051
└── Dockerfile                # Imagem Alpine Nginx
```

### 2. Tela de Upload / Dashboard / Relatório
Tudo integrado via abas dentro da `index.html`. 
As chamadas HTTP são feitas via `fetch` redirecionadas pelo proxy do `nginx.conf`.

### 3. Dockerfile
- Base: `nginx:alpine`
- Copia da `nginx.conf`
- Copia de HTML/CSS/JS para `/usr/share/nginx/html`
- Expõe porta `8051`

## REQUISITOS DE UX CUMPRIDOS
- Interface "Vibe Cyberpunk / Moderna"
- Mensagens de erro com Toasts
- Sidebar com navegação clara

*Este documento foi atualizado para refletir a substituição do Streamlit por Web App Nativo.*