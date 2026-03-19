# Arch Analyzer - Frontend

Frontend em Streamlit para o sistema de análise automatizada de diagramas de arquitetura.

## Estrutura

```
frontend/
├── app.py                    # Entry point principal
├── pages/
│   ├── 1_upload.py           # Tela de upload
│   ├── 2_dashboard.py        # Dashboard de acompanhamento
│   └── 3_report.py           # Relatório + Feedback
├── services/
│   └── api_client.py         # Cliente HTTP para API
├── components/
│   └── status_badge.py       # Componente de status
├── .streamlit/
│   └── config.toml           # Configuração do tema
├── requirements.txt
├── Dockerfile
└── README.md
```

## Quick Start

### 1. Instalação local

```bash
cd frontend
pip install -r requirements.txt

# Configure a URL do backend
export BACKEND_URL=http://localhost:8001

# Execute
streamlit run app.py
```

### 2. Docker

```bash
cd frontend
docker build -t arch-analyzer-frontend .
docker run -p 8501:8501 \
  -e BACKEND_URL=http://localhost:8001 \
  arch-analyzer-frontend
```

## Funcionalidades

### 📤 Upload
- Upload de imagens (PNG, JPG, JPEG) e PDFs
- Pré-visualização do arquivo
- Validação de tamanho (máx. 10MB)
- Status imediato após envio

### 📊 Dashboard
- Lista de todas as análises
- Métricas em tempo real
- Filtros por status
- Auto-refresh (5 segundos)
- Badges coloridos por status

### 📄 Relatório
- Visualização completa do relatório
- Componentes identificados
- Riscos arquiteturais
- Recomendações
- Exportação (JSON/Markdown)
- Sistema de feedback (1-5 estrelas)

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `BACKEND_URL` | `http://localhost:8001` | URL base da API |

## Tema

O frontend usa um tema escuro profissional otimizado para demonstrações em vídeo:
- Background: `#0e1117`
- Accent: `#58a6ff`
- Cards: `#161b22`

## API Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/upload` | Upload de diagrama |
| GET | `/api/v1/analysis/{id}/status` | Status da análise |
| GET | `/api/v1/reports` | Lista de relatórios |
| GET | `/api/v1/reports/{id}` | Detalhe do relatório |
| POST | `/api/v1/reports/{id}/feedback` | Enviar feedback |

## Desenvolvimento

Para executar em modo de desenvolvimento com hot-reload:

```bash
streamlit run app.py --server.runOnSave true
```

## Docker Compose Integration

Adicione ao seu `docker-compose.yml`:

```yaml
frontend:
  build: ./frontend
  ports:
    - "8501:8501"
  environment:
    - BACKEND_URL=http://upload-service:8001
  depends_on:
    - upload-service