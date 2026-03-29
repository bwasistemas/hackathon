# Arch Analyzer

Sistema de análise automatizada de diagramas de arquitetura de software para hackathon acadêmico.

## Arquitetura

``` text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend       │────▶│  Upload Service  │────▶│    RabbitMQ     │
│  (Nginx/SPA)    │     │   (FastAPI)      │     │   (Message Q)   │
│   :8051         │     │   :8001          │     │   :5672/:15672  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
           ┌─────────────────────────────────────────────┘
           │
           ▼
┌──────────────────┐          ┌──────────────────┐        ┌─────────────────┐
│   AI Service     │          │   PostgreSQL     │        │     MinIO       │
│   (LLM + OCR)    │─────────▶│   :5432          │        │  :9000/:9001    │
│   :8003          │          └──────────────────┘        └─────────────────┘
└──────────────────┘                 ▲
           │                         │
           └─────────────────────────┘
                                     │
┌──────────────────┐          ┌──────────────────┐
│  Report Service  │◀─────────│   Prometheus     │
│   (FastAPI)      │          │   + Grafana      │
│   :8004          │          │   :9090/:3000    │
└──────────────────┘          └──────────────────┘
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
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin |
| **MinIO API** | http://localhost:9000 | minioadmin / minioadmin |
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
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
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

Resumo:
1. Upload Service (Porta 8001)
É a Esteira de Entrada. Quando você seleciona o seu PDF e clica em Enviar, ele salva o seu arquivo numa pasta, vai no Banco de Dados (Postgres) e anota: "O Bruno enviou o arquivo X. Status = RECEIVED". Imediatamente, ele envia um "Bipe" pra fila do RabbitMQ avisando: "Tem diagrama novo na área". E o trabalho dele acaba aí.

2. AI Service (Porta 8003) - O Cérebro da Operação
Esse é o verdadeiro cara que GERA o relatório. Ele fica invisível no background ouvindo a fila do RabbitMQ o tempo todo:

Quando o RabbitMQ apita, o AI Service acorda, puxa o seu PDF da pasta e roda a lib Poppler + Tesseract (OCR) em Multithreading para extrair o conteúdo gigante em texto.
Depois ele pega o texto, conecta lá na nuvem do OpenRouter, joga para a LLM (DeepSeek Vision) e pede análise de Risco e Componentes.
O DeepSeek devolve o veredito em formato JSON e aí o AI Service vai lá na mesma tabela do Banco de Dados e diz: "Muda o Status pra DONE, e salva esse texto brutal que a IA me devolveu na coluna file_path".

3. Report Service (Porta 8004)
É a Estante de Leitura (que tem o Swagger ali no seu link!). Ele não processa IA, ele NUNCA aciona a API do DeepSeek nem lê PDF. A única coisa que ele faz é ir no Banco de Dados (Postgres), consultar tudo que está com as tags PROCESSING ou DONE e devolver mastigadinho em um Array JSON para o Frontend colocar bonitinho no seu Dashboard.

Resumindo: Você enviou para o Upload Service, o AI Service suou a camisa gerando e lendo a IA demoradamente no "background", e o Report Service só serviu de "garçom" para trazer as Análises já prontas e salvas do banco de dados pra sua tela do Dashboard! Tudo em frações de segundos desacopladas!