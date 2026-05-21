# Visão geral da aplicação

## Propósito

O **Arch Analyzer** é um sistema distribuído que recebe diagramas de arquitetura (imagens ou PDF), extrai texto por OCR multimodal com LLM, analisa com um swarm de agentes e devolve um relatório estruturado: componentes identificados, riscos arquiteturais e resumo. Cada serviço possui banco de dados dedicado e se comunica por HTTP (com JWT) ou por filas AMQP — nunca por acesso direto ao banco alheio.

## Arquitetura em alto nível

O sistema segue o padrão de **microsserviços** com **arquitetura hexagonal** em cada serviço:

- **Frontend** (SPA estática servida por Nginx): painel de upload, acompanhamento de status, relatórios e feedback. Proxy reverso para as APIs na mesma origem.
- **Upload Service**: recebe arquivos, persiste metadados em `arch_uploads`, publica `diagram.upload` no RabbitMQ e consome `diagram.result` para atualizar o status.
- **AI Service**: consome `diagram.upload`, executa OCR multimodal + swarm Strands, publica `diagram.result`. **Sem banco de dados próprio.**
- **Report Service**: serve relatórios lendo o Upload Service via HTTP (JWT service-to-service). Persiste feedback em `arch_reports`.
- **PostgreSQL**: dois bancos dedicados na mesma instância — `arch_uploads` e `arch_reports`.
- **RabbitMQ**: broker AMQP com duas filas: `diagram.upload` e `diagram.result`.
- **MinIO**: object storage S3-compatible para os arquivos enviados.
- **Prometheus / Grafana / Loki / Promtail**: métricas HTTP, dashboards e logs dos containers.

## Fluxo principal

```
Analista
  │ POST /upload (JWT)
  ▼
Frontend (Nginx :8051)
  │ proxy /upload-service/
  ▼
Upload Service (:8001)
  ├─ PUT arquivo → MinIO
  ├─ INSERT uploads (status=RECEIVED) → arch_uploads
  └─ Publica diagram.upload → RabbitMQ
                                  │
                                  ▼
                            AI Service (:8003)
                              ├─ Publica diagram.result {PROCESSING} → RabbitMQ
                              ├─ GET arquivo ← MinIO
                              ├─ OCR multimodal (Gemma 4 26B) + swarm Strands (DeepSeek v3.2)
                              └─ Publica diagram.result {DONE, payload_json} → RabbitMQ
                                  │
                                  ▼ (consome diagram.result)
                            Upload Service
                              └─ UPDATE uploads (status=DONE, file_path=payload_json)

Analista
  │ GET /reports/{id} (JWT)
  ▼
Frontend
  │ proxy /report-service/
  ▼
Report Service (:8004)
  ├─ GET /uploads/{id} → Upload Service (JWT s2s)
  └─ retorna ReportResponse {analysis, status, filename}
```

## Serviços e portas

| Serviço | Porta | Função |
|---------|-------|--------|
| Frontend | 8051 | SPA + proxy reverso |
| Upload Service | 8001 | Upload, JWT, fila, status |
| AI Service | 8003 | OCR + LLM + publicador de resultado |
| Report Service | 8004 | Relatórios via HTTP s2s + feedback |
| RabbitMQ AMQP | 5672 | Broker de mensagens |
| RabbitMQ Management | 15672 | Interface de administração |
| PostgreSQL | 5432 | arch_uploads + arch_reports |
| MinIO API | 9000 | Object storage S3 |
| MinIO Console | 9001 | Interface de administração |
| Prometheus | 9090 | Coleta de métricas |
| Grafana | 3000 | Dashboards |
| Loki | 3100 | Armazenamento de logs |

## Bancos de dados

| Banco | Dono | Tabelas | Criação |
|-------|------|---------|---------|
| `arch_uploads` | Upload Service | `uploads`, `users` | `POSTGRES_DB` env (fresh) ou `initContainer create-db` (k8s) / `postgres-setup` (Compose) |
| `arch_reports` | Report Service | `feedback` | `init-databases.sh` (fresh) ou `initContainer create-db` (k8s) / `postgres-setup` (Compose) |

Nenhum serviço acessa o banco do outro. A comunicação entre Report Service e Upload Service ocorre exclusivamente via HTTP REST com JWT.

## Filas RabbitMQ

| Fila | Publisher | Consumer | Payload |
|------|-----------|----------|---------|
| `diagram.upload` | Upload Service | AI Service | `{upload_id, filename, file_path, content_type}` |
| `diagram.result` | AI Service | Upload Service | `{upload_id, status, payload_json?, error_message?}` |

Ambas as filas são declaradas com `durable=True` e mensagens com `DeliveryMode.PERSISTENT`.

## Autenticação

- **JWT emitido pelo Upload Service** (`POST /token`). O mesmo `JWT_SECRET_KEY` é configurado em todos os serviços.
- **Service-to-service (s2s)**: o Report Service obtém um token via `POST /token` com `UPLOAD_SERVICE_USER`/`UPLOAD_SERVICE_PASSWORD` e o renova automaticamente 60 s antes do vencimento.
- **Rate limiting** por IP via SlowAPI em todos os serviços FastAPI.

## Configuração

Variáveis centralizadas em `infrastructure/.env` (ver `infrastructure/.env.example`):

| Variável | Usado por | Descrição |
|----------|-----------|-----------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Upload, Report | Credenciais do PostgreSQL |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | Upload, AI | Credenciais do RabbitMQ |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Upload, AI, Report | Credenciais do MinIO |
| `MINIO_BUCKET` | Upload, AI, Report | Bucket (padrão: `fiap`) |
| `JWT_SECRET_KEY` | Upload, AI, Report | Segredo compartilhado JWT (mínimo 32 chars) |
| `ADMIN_USER` / `ADMIN_PASSWORD` | Upload | Credenciais do usuário padrão |
| `UPLOAD_SERVICE_URL` | Report | URL do Upload Service para chamadas s2s |
| `UPLOAD_SERVICE_USER` / `UPLOAD_SERVICE_PASSWORD` | Report | Credenciais s2s (normalmente = `ADMIN_USER`/`PASSWORD`) |
| `OPENAI_API_KEY` | AI | Chave do provedor LLM |
| `OPENAI_BASE_URL` | AI | URL base do provedor (OpenRouter em produção) |
| `LLM_MODEL` | AI | Modelo de análise (padrão: `deepseek/deepseek-v3.2`) |
| `LLM_OCR` | AI | Modelo de OCR multimodal (padrão: `google/gemma-4-26b-a4b-it`) |
| `ALLOWED_ORIGINS` | Upload, AI, Report | Origens CORS permitidas |

## Observabilidade

- **Métricas**: endpoints `/metrics` em todos os serviços FastAPI (`prometheus-fastapi-instrumentator`). Prometheus coleta via scrape; no Kubernetes usa auto-descoberta por annotations de pod.
- **Logs**: JSON estruturado com `timestamp`, `level`, `service`, `name`, `message`. Promtail coleta e envia ao Loki. Grafana expõe dashboards de métricas e logs.

## Deploy

| Ambiente | Tecnologia | Namespaces |
|----------|-----------|------------|
| Local | Docker Compose | — |
| Produção / Homologação | Kubernetes (Kind na VPS) | `arch-prod` (main), `arch-hmg` (hmg) |
| Observabilidade | Kubernetes | `arch-geral` (compartilhado, não rotacionado) |

Pipeline CI/CD: GitHub Actions → testes em paralelo → build/push GHCR → deploy via SSH + kubectl. O AI Service escala automaticamente no Kubernetes via KEDA com base no tamanho da fila `diagram.upload`.

## Como executar

```bash
# Setup local completo
cp infrastructure/.env.example infrastructure/.env
# Edite infrastructure/.env

chmod +x setup.sh && ./setup.sh   # Linux/macOS
# ou
chmod +x wsl-setup.sh && ./wsl-setup.sh   # WSL
```

Ver instruções detalhadas no [`README.md`](../README.md) da raiz.
