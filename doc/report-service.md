# Report Service — arquitetura hexagonal

## Visão geral

O **Report Service** expõe os relatórios de análise gerados pelo AI Service e gerencia o feedback dos analistas. Ele **não possui banco de dados de uploads** — lê os dados de upload exclusivamente via HTTP do Upload Service (autenticado com JWT service-to-service). O único banco próprio é `arch_reports`, que armazena apenas a tabela `feedback`.

Porta: **8004** | Framework: FastAPI | Banco: `arch_reports` (PostgreSQL)

## Estrutura hexagonal

```
report-service/app/
├── domain/
│   ├── models.py          # Report, ReportSummary, Statistics
│   └── exceptions.py      # ReportNotFoundError, InvalidRatingError, UploadNotFoundError, …
├── application/
│   ├── ports.py           # ReportRepositoryPort, FeedbackRepositoryPort
│   └── report_management.py  # Casos de uso
├── adapters/
│   ├── inbound/
│   │   ├── http_routes.py  # Rotas FastAPI
│   │   └── schemas.py      # Pydantic schemas
│   ├── outbound/
│   │   ├── http_upload_client.py  # HttpUploadClientAdapter (s2s JWT)
│   │   ├── asyncpg_reports.py     # AsyncpgFeedbackRepository
│   │   └── minio_storage.py       # MinIOStorage (download de attachments)
│   └── helpers/
│       └── auth.py                # Verificação JWT (não emite tokens)
├── bootstrap.py           # Composition root
├── config.py              # Settings
└── main.py                # Entrypoint uvicorn
```

## Domínio

### Modelos (`domain/models.py`)

| Modelo | Campos principais |
|--------|-------------------|
| `Report` | `id`, `filename`, `status`, `analysis` (dict), `created_at`, `minio_url`, `content_type` |
| `ReportSummary` | `id`, `filename`, `status`, `created_at` |
| `Statistics` | `total_uploads`, `by_status` (dict), `avg_rating`, `total_feedback` |

## Portas (application/ports.py)

| Porta | Implementação | Métodos |
|-------|--------------|---------|
| `ReportRepositoryPort` | `HttpUploadClientAdapter` | `get_report`, `list_reports`, `check_upload_exists`, `get_upload_counts` |
| `FeedbackRepositoryPort` | `AsyncpgFeedbackRepository` | `create_feedback`, `get_feedback_stats` |

> **Separação clara**: `ReportRepositoryPort` lê uploads via HTTP externo; `FeedbackRepositoryPort` grava no banco local. Nenhuma consulta direta ao `arch_uploads`.

## Casos de uso (application/report_management.py)

| Caso de uso | Descrição |
|-------------|-----------|
| `GetReportUseCase` | Obtém relatório de um upload via `ReportRepositoryPort.get_report`. Lança `ReportNotFoundError` se não encontrado |
| `ListReportsUseCase` | Lista relatórios com filtro opcional de status via `ReportRepositoryPort.list_reports` |
| `SubmitFeedbackUseCase` | Valida rating (1-5), verifica existência do upload via `check_upload_exists`, persiste via `FeedbackRepositoryPort.create_feedback` |
| `GetStatisticsUseCase` | Combina contagens de upload (via `get_upload_counts`) com estatísticas de feedback (via `get_feedback_stats`) em um `Statistics` unificado |

### GetStatisticsUseCase — fontes de dados

```
execute()
  ├─ report_repository.get_upload_counts()
  │    → GET /stats/uploads (Upload Service, JWT s2s)
  │    → {total: int, by_status: {status: count}}
  ├─ feedback_repository.get_feedback_stats()
  │    → SELECT AVG(rating), COUNT(*) FROM feedback (arch_reports)
  │    → {avg_rating: float, total_feedback: int}
  └─ Retorna Statistics(total_uploads, by_status, avg_rating, total_feedback)
```

## Adaptadores

### Saída (outbound)

#### HttpUploadClientAdapter (`http_upload_client.py`)

Implementa `ReportRepositoryPort`. Faz chamadas HTTP ao Upload Service com JWT service-to-service.

**Gerenciamento de token s2s:**
- Obtém token via `POST /token` com `UPLOAD_SERVICE_USER`/`UPLOAD_SERVICE_PASSWORD`
- Armazena em `_token` e `_token_expires_at` (monotonic clock)
- Renova automaticamente **60 segundos antes** do vencimento (janela de 30 min − 60 s)
- `NullReportRepository` — no-op de fallback quando Upload Service está indisponível

| Método | Chamada HTTP |
|--------|-------------|
| `get_report(upload_id)` | `GET /uploads/{id}` → decodifica `file_path` como JSON de análise |
| `list_reports(status, limit)` | `GET /uploads?limit=N` → filtra por status localmente |
| `check_upload_exists(upload_id)` | `GET /uploads/{id}` → verifica HTTP 200 |
| `get_upload_counts()` | `GET /stats/uploads` → retorna dict com totais |

#### AsyncpgFeedbackRepository (`asyncpg_reports.py`)

Implementa `FeedbackRepositoryPort`. Pool asyncpg (min 2, max 10) no banco `arch_reports`.

- Cria tabela `feedback` automaticamente (`CREATE TABLE IF NOT EXISTS`).
- `create_feedback`: `INSERT INTO feedback (upload_id, rating, comment)`.
- `get_feedback_stats`: `SELECT AVG(rating)::float, COUNT(*) FROM feedback`.

#### MinIOStorage (`minio_storage.py`)

Usado exclusivamente pelo endpoint `/reports/{id}/attachment` para fazer download do arquivo original e retorná-lo ao cliente.

### Entrada (inbound)

#### HTTP — `http_routes.py`

| Rota | Método | Auth | Descrição |
|------|--------|------|-----------|
| `/health` | GET | — | Health check público |
| `/health/db` | GET | JWT | Verifica conexão ao `arch_reports` |
| `/reports/{id}` | GET | JWT | Detalhe do relatório (`GetReportUseCase`). Rate limit: 10/min |
| `/reports/{id}/attachment` | GET | JWT | Download do arquivo original via MinIO |
| `/reports` | GET | JWT | Lista relatórios (`ListReportsUseCase`). Query: `status`, `limit` (1-100) |
| `/feedback` | POST | JWT | Envia feedback (`SubmitFeedbackUseCase`). Body: `{upload_id, rating, comment?}` |
| `/stats` | GET | JWT | Estatísticas combinadas (`GetStatisticsUseCase`) |
| `/metrics` | GET | — | Métricas Prometheus |

**Autenticação**: este serviço **não emite tokens**. O `tokenUrl` do OAuth2PasswordBearer aponta para `/upload-service/token` (informativo para o Swagger UI). Todos os tokens são verificados com o `JWT_SECRET_KEY` compartilhado.

## Banco de dados — `arch_reports`

| Tabela | Colunas | Criação |
|--------|---------|---------|
| `feedback` | `id SERIAL PK`, `upload_id UUID`, `rating INT (1-5)`, `comment TEXT`, `created_at` | `CREATE TABLE IF NOT EXISTS` no startup |

O banco `arch_reports` é criado pelo `postgres-setup` (Docker Compose) ou `initContainer create-db` (Kubernetes) antes do serviço iniciar.

## Bootstrap (`bootstrap.py`)

Sequência de inicialização no `lifespan`:

1. `create_feedback_repository(DATABASE_URL)` → `AsyncpgFeedbackRepository` + pool asyncpg
2. `MinIOStorage(settings)` — armazenado em `app.state.minio_storage`
3. `HttpUploadClientAdapter(base_url, username, password)` — implementa `ReportRepositoryPort`
4. Instancia os 4 casos de uso com dependências injetadas
5. `yield` — serviço ativo

Na finalização: fecha pool asyncpg.

## Middlewares e segurança

| Middleware | Função |
|------------|--------|
| `SecurityHeadersMiddleware` | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `HSTS` |
| `SlowAPIMiddleware` | Rate limiting por IP |
| `CORSMiddleware` | Origens via `ALLOWED_ORIGINS`; rejeita wildcard com credenciais |

## Variáveis de ambiente relevantes

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/arch_reports` |
| `UPLOAD_SERVICE_URL` | URL base do Upload Service (ex.: `http://upload-service:8001`) |
| `UPLOAD_SERVICE_USER` | Usuário para obtenção do token s2s |
| `UPLOAD_SERVICE_PASSWORD` | Senha para obtenção do token s2s |
| `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` | Object storage (somente leitura para attachments) |
| `JWT_SECRET_KEY` | Segredo compartilhado para verificação de tokens |
| `ALLOWED_ORIGINS` | Origens CORS |
