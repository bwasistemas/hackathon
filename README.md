# Arch Analyzer

Sistema de análise automatizada de diagramas de arquitetura de software para hackathon acadêmico.

## Arquitetura

``` text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│  Upload Service  │────▶│    RabbitMQ     │
│  (Nginx/SPA)    │     │   (FastAPI)      │     │   (Message Q)   │
│   :8051         │     │   :8001          │     │   :5672/:15672  │
└─────────────────┘     └───────┬──────────┘     └────────┬────────┘
                                │                         │
                                │ store file              │ notify
                                ▼                         ▼
                        ┌─────────────────┐     ┌──────────────────┐
                        │     MinIO       │◀────│   AI Service     │
                        │  (Object Store) │     │   (LLM + OCR)    │
                        │  :9000/:9001    │     │   :8003          │
                        └─────────────────┘     └───────┬──────────┘
                                                        │
                                                        │ persist result
                                                        ▼
┌──────────────────┐                          ┌──────────────────┐
│  Report Service  │◀─────────────────────────│   PostgreSQL     │
│   (FastAPI)      │                          │   :5432          │
│   :8004          │                          └──────────────────┘
└──────────────────┘
        ▲
        │
┌──────────────────┐
│  Prometheus      │
│  + Grafana       │
│  :9090/:3000     │
└──────────────────┘
```

## Quick Start

### 1. Clone e configure

```bash
git clone <repository-url>
cd Hachaton

# Copie o arquivo de exemplo de variáveis de ambiente
cp infrastructure/.env.example infrastructure/.env

# Edite o .env com suas credenciais
nano infrastructure/.env
```

### 2. Suba todos os serviços

```bash
# Opção 1: Script automático (recomendado)
chmod +x setup.sh && ./setup.sh

# Opção 2: Docker Compose direto
cd infrastructure && docker-compose up -d

# Opção 3: Build manual + up
cd infrastructure
docker-compose build
docker-compose up -d
```

### 3. Acesse os serviços

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| **Frontend** | http://localhost:8051 | - |
| **Upload API** | http://localhost:8001/docs | - |
| **AI API** | http://localhost:8003/docs | - |
| **Report API** | http://localhost:8004/docs | - |
| **RabbitMQ** | http://localhost:15672 | fiap / fiap |
| **PostgreSQL** | localhost:5432 | fiap / fiap |
| **MinIO Console** | http://localhost:9001 | fiap / fiap1234 |
| **MinIO API** | http://localhost:9000 | fiap / fiap1234 |
| **Prometheus** | http://localhost:9090 | - |
| **Grafana** | http://localhost:3000 | fiap / fiap |

## Estrutura do Projeto

```
Hachaton/
├── frontend/                    # Interface Single Page App (Nginx)
│   ├── index.html              # Entry point central de comandos
│   ├── styles.css              # Estilos UI modernos
│   ├── script.js               # Lógica Vanilla JS
│   ├── nginx.conf              # Config do Web Server
│   └── Dockerfile
│
├── infrastructure/             # Docker & Observabilidade
│   ├── docker-compose.yml      # Orquestração de serviços
│   ├── dockerfiles/            # Dockerfiles dos microsserviços
│   ├── prometheus/             # Configuração Prometheus
│   ├── grafana/                # Dashboards + Provisioning
│   ├── .github/workflows/       # CI/CD
│   ├── .env.example
│   └── README.md
│
├── services/                   # Código das APIs
│   ├── upload-service/         # Recebe e valida arquivos
│   ├── ai-service/             # Multi-task worker: Consome RabbitMQ, OCR(PDF/Img) e aciona LLM
│   └── report-service/         # Serve análises persistidas no Postgres
│
├── setup.sh                    # Script de setup rápido
├── README.md                   # Este arquivo
├── Setup.md                    # Especificação da infraestrutura
└── Frontend.md                 # Especificação do frontend
```

## Configuração

### Variáveis de Ambiente

Edite `infrastructure/.env`:

```env
# Database
POSTGRES_USER=fiap
POSTGRES_PASSWORD=fiap

# RabbitMQ
RABBITMQ_USER=fiap
RABBITMQ_PASSWORD=fiap

# AI/LLM
OPENAI_API_KEY=sua_chave_do_openrouter_ou_openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat

# Grafana
GRAFANA_USER=fiap
GRAFANA_PASSWORD=fiap

# MinIO (Object Storage)
MINIO_ROOT_USER=fiap
MINIO_ROOT_PASSWORD=fiap1234
```

## Funcionalidades

### Upload de Diagramas
- Suporte a PNG, JPG, JPEG, PDF
- Limite de 10MB por arquivo
- Pré-visualização antes do envio
- Armazenamento de arquivos no MinIO

### Processamento (AI Service Unificado)
- Consumo assíncrono via RabbitMQ (`aio-pika`).
- OCR avançado com Tesseract e suporte nativo a PDFs via `pdf2image` e `poppler-utils`.
- Extração de insights arquiteturais via IA (Estrutura JSON Restritiva via Pydantic).

### Dashboard
- Status em tempo real
- Métricas de análises
- Filtros por status
- Auto-refresh

### Relatórios
- Componentes identificados
- Riscos arquiteturais
- Recomendações
- Exportação JSON/Markdown

### Feedback
- Sistema de avaliação 1-5 estrelas
- Comentários opcionais

## Observabilidade

### Prometheus
- Métricas de todos os serviços FastAPI
- Scraping automático configurado

### Grafana
- Dashboard pré-configurado
- Datasource Prometheus automático
- Métricas de Request Rate, Latência p95, Status

## CI/CD

Pipeline GitHub Actions configurado:
1. Lint (ruff, black)
2. Testes unitários
3. Build de imagens Docker
4. Push para ghcr.io
5. Deploy automático (develop)

## Desenvolvimento Local

### Sem Docker (usando servidor estático leve, ex: Python)

```bash
# Backend
cd services/upload-service
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
python -m http.server 8051
# Acesse http://localhost:8051
```

### Com Docker

```bash
# Build individual
docker build -t arch-analyzer-upload ./infrastructure/dockerfiles/Dockerfile.upload

# Run
docker run -p 8001:8001 arch-analyzer-upload
```

## Troubleshooting

### Serviços não sobem
```bash
docker-compose logs <servico>
docker-compose ps
```

### Erro de conexão com banco
Verifique se o PostgreSQL está saudável:
```bash
docker-compose ps postgres
docker-compose logs postgres
```

### RabbitMQ não conecta
```bash
docker-compose logs rabbitmq
# Verifique credenciais no .env
```

### MinIO não conecta
```bash
docker-compose logs minio
# Verifique as credenciais no .env
# Console: http://localhost:9001
```

## MinIO (Object Storage)

### Listar arquivos
```bash
# Via mc (minio client)
docker exec arch-analyzer-minio mc ls local/fiap/

# Via curl
curl -s http://localhost:9000/fiap/ -u fiap:fiap1234
```

### Baixar arquivo
```bash
# Via curl (salva no diretório atual)
curl -O http://localhost:9000/fiap/arquivo.png -u fiap:fiap1234

# Via docker cp
docker cp arch-analyzer-minio:/tmp/arquivo.png ./arquivo.png

# Via mc
docker exec arch-analyzer-minio mc cp local/fiap/arquivo.png /tmp/
docker cp arch-analyzer-minio:/tmp/arquivo.png ./arquivo.png
```

### Upload de arquivo
```bash
# Via curl
curl -X PUT http://localhost:9000/fiap/arquivo.png \
  -u fiap:fiap1234 \
  -T ./arquivo.png

# Via mc
docker exec -i arch-analyzer-minio mc cp ./arquivo.png local/fiap/
```

**Credenciais:** `fiap` / `fiap1234`
**Bucket padrão:** `fiap`

### Frontend não conecta no backend
```bash
# Verifique o Nginx config e a integridade da conexão via Docker logs
docker-compose logs frontend
# O frontend agora roteia as chamadas para o backend internamente via Nginx.
```

## Segurança

- Mude todas as senhas padrão em produção!
- Não commite o arquivo `.env`
- Use credenciais diferentes para produção
- Porta 5432 (PostgreSQL) não deve ser exposta

## Licença

MIT - Hackathon FIAP 2026

## Como funciona o fluxo completo

### 1. Upload Service (Porta 8001)
É a esteira de entrada. Quando você seleciona um PDF/imagem e clica em Enviar:
- Faz o upload do arquivo direto para o **MinIO** (Object Storage S3-compatible)
- Registra no PostgreSQL: `status = RECEIVED` e salva a URL do MinIO (`minio_url`)
- Publica uma mensagem no **RabbitMQ** avisando que tem diagrama novo para processar

### 2. AI Service (Porta 8003)
O cérebro da operação. Fica em background consumindo a fila do RabbitMQ:
- Ao receber uma mensagem, **baixa o arquivo direto do MinIO** via `minio_url`
- Roda OCR com Poppler + Tesseract (multithreading) para extrair o texto do PDF/imagem
- Envia o conteúdo para a LLM (DeepSeek via OpenRouter) pedindo análise de componentes e riscos
- Persiste o resultado em JSON no PostgreSQL e atualiza o status para `DONE`

### 3. Report Service (Porta 8004)
O garçom. Não processa IA nem acessa o MinIO. Apenas consulta o PostgreSQL e devolve as análises prontas em JSON para o Frontend exibir no Dashboard.