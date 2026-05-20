# Upload Service — arquitetura hexagonal

## Visão geral

O **Upload Service** é o ponto de entrada principal do sistema. Ele autentica usuários, recebe arquivos de diagrama, persiste metadados no PostgreSQL (`arch_uploads`), armazena os arquivos no MinIO e dispara o fluxo de análise via RabbitMQ. Também consome a fila `diagram.result` para atualizar o status de cada upload conforme o AI Service processa.

Porta: **8001** | Framework: FastAPI | Banco: `arch_uploads` (PostgreSQL)

## Estrutura hexagonal

```
upload-service/app/
├── domain/
│   ├── models.py          # Upload, UploadResult
│   └── exceptions.py      # FileTooLargeError, StorageError, MessageQueueError, …
├── application/
│   ├── ports.py           # StoragePort, UploadRepositoryPort, MessagePublisherPort
│   └── upload_file.py     # Casos de uso
├── adapters/
│   ├── inbound/
│   │   ├── http_routes.py           # Rotas FastAPI (HTTP)
│   │   ├── rabbitmq_result_consumer.py  # Consumidor AMQP (diagram.result)
│   │   └── schemas.py               # Pydantic schemas
│   ├── outbound/
│   │   ├── asyncpg_uploads.py       # AsyncpgUploadRepository
│   │   ├── minio_storage.py         # MinIOStorageAdapter
│   │   └── rabbitmq_publisher.py    # RabbitMQPublisher
│   └── helpers/
│       └── auth.py                  # JWT (emissão e verificação)
├── bootstrap.py           # Composition root
├── config.py              # Settings (lê env vars)
└── main.py                # Entrypoint uvicorn
```

## Domínio

### Modelos (`domain/models.py`)

| Modelo | Campos principais |
|--------|-------------------|
| `Upload` | `id`, `filename`, `content_type`, `file_size`, `status`, `file_path`, `minio_url`, `created_at`, `updated_at` |
| `UploadResult` | `id`, `filename`, `status`, `message`, `minio_url` |

### Ciclo de vida do status

```
RECEIVED → PROCESSING → DONE
                      ↘ ERROR
```

- `RECEIVED` — arquivo salvo no MinIO, metadados gravados, evento publicado
- `PROCESSING` — AI Service confirmou que iniciou o processamento
- `DONE` — AI Service publicou resultado; `file_path` passa a conter o JSON de análise
- `ERROR` — AI Service reportou falha; `file_path` contém `{"text": "", "ai": {"error": "..."}}`

## Portas (application/ports.py)

| Porta | Métodos principais |
|-------|--------------------|
| `StoragePort` | `upload_file(content, object_name, content_type) → str` |
| `UploadRepositoryPort` | `create_upload`, `get_upload`, `list_uploads`, `update_status`, `mark_processing`, `mark_done_with_payload`, `mark_failed`, `get_upload_stats` |
| `MessagePublisherPort` | `publish_upload_event(upload_id, filename, file_path, content_type)` |

## Casos de uso (application/upload_file.py)

| Caso de uso | Descrição |
|-------------|-----------|
| `UploadFileUseCase` | Valida tamanho (≤ 10 MB), gera UUID, salva no MinIO, cria registro `RECEIVED` no banco e publica `diagram.upload` |
| `ListUploadsUseCase` | Retorna até 50 uploads recentes em ordem decrescente de criação |
| `GetUploadUseCase` | Retorna um upload por ID |
| `UpdateUploadResultUseCase` | Atualiza status a partir de mensagem `diagram.result` (`PROCESSING`, `DONE`, `ERROR`) |
| `GetUploadStatsUseCase` | Agrega contagem por status (`{total, by_status}`) |

### UploadFileUseCase — fluxo interno

```
execute(filename, content, content_type)
  1. Valida len(content) ≤ MAX_FILE_SIZE (10 MB) → FileTooLargeError
  2. Gera upload_id = uuid4()
  3. storage.upload_file(content, "uploads/{id}_{filename}", content_type) → minio_url
  4. repository.create_upload(upload_id, filename, ..., status=RECEIVED)
  5. publisher.publish_upload_event(upload_id, filename, minio_url, content_type)
  6. Retorna UploadResult(id, filename, status="RECEIVED", ...)
```

## Adaptadores

### Saída (outbound)

#### AsyncpgUploadRepository (`asyncpg_uploads.py`)

Implementa `UploadRepositoryPort` com pool asyncpg (min 2, max 10 conexões).

- Cria a tabela `uploads` automaticamente na inicialização (`CREATE TABLE IF NOT EXISTS`).
- `mark_done_with_payload`: grava o JSON de análise em `file_path` e atualiza `status = DONE`.
- `mark_failed`: grava `{"text": "", "ai": {"error": "..."}}` em `file_path` e `status = ERROR`.
- `get_upload_stats`: `COUNT(*)` total + `GROUP BY status`.
- `NullUploadRepository` — no-op usado como fallback quando o banco está indisponível na inicialização.

#### MinIOStorageAdapter (`minio_storage.py`)

Implementa `StoragePort`. Faz PUT do arquivo no bucket configurado (`MINIO_BUCKET`) e retorna o `object_name` como URL lógica.

#### RabbitMQPublisher (`rabbitmq_publisher.py`)

Implementa `MessagePublisherPort`. Declara a fila `diagram.upload` com `durable=True` antes de publicar; usa `DeliveryMode.PERSISTENT` para garantir que mensagens sobrevivam a restart do broker.

- `NullMessagePublisher` — no-op de fallback quando RabbitMQ está indisponível.

### Entrada (inbound)

#### HTTP — `http_routes.py`

| Rota | Método | Auth | Descrição |
|------|--------|------|-----------|
| `/health` | GET | — | Health check público |
| `/token` | POST | — | Emite JWT (OAuth2 password flow). Rate limit: 5/min |
| `/upload` | POST | JWT | Recebe arquivo, executa `UploadFileUseCase`. Rate limit: 5/min |
| `/uploads` | GET | JWT | Lista uploads recentes (`ListUploadsUseCase`) |
| `/uploads/{id}` | GET | JWT | Detalhe de upload (`GetUploadUseCase`) |
| `/stats/uploads` | GET | JWT | Contagem por status (`GetUploadStatsUseCase`) |
| `/metrics` | GET | — | Métricas Prometheus (prometheus-fastapi-instrumentator) |

**Autenticação**: este serviço é o **único emissor de tokens JWT** em todo o sistema. Os demais serviços apenas verificam tokens com o `JWT_SECRET_KEY` compartilhado. O endpoint `/token` usa `secrets.compare_digest` para comparação em tempo constante.

#### RabbitMQ Consumer — `rabbitmq_result_consumer.py`

Consome `diagram.result` (durable, `prefetch_count=1`). Para cada mensagem:
1. Decodifica JSON: `{upload_id, status, payload_json?, error_message?}`
2. Chama `UpdateUploadResultUseCase.execute(...)` que roteia para `mark_processing`, `mark_done_with_payload` ou `mark_failed` conforme o `status`.
3. Ack automático ao sair do bloco `message.process()`.

## Banco de dados — `arch_uploads`

| Tabela | Colunas | Criação |
|--------|---------|---------|
| `uploads` | `id UUID PK`, `filename`, `content_type`, `file_size`, `status`, `file_path` (JSON ao final), `minio_url`, `created_at`, `updated_at` | `CREATE TABLE IF NOT EXISTS` no startup |

O banco `arch_uploads` é criado pelo `postgres-setup` (Docker Compose) ou `initContainer create-db` (Kubernetes) antes do serviço iniciar.

## Bootstrap (`bootstrap.py`)

Sequência de inicialização no `lifespan`:

1. `create_upload_repository(DATABASE_URL)` → `AsyncpgUploadRepository` + pool asyncpg
2. `MinIOStorageAdapter(settings)`
3. `connect_rabbitmq(...)` → `aio_pika.RobustConnection`
4. `RabbitMQPublisher(connection)`
5. Instancia os 5 casos de uso com suas dependências injetadas
6. `start_diagram_result_consumer(connection, update_result_use_case)` — inicia consumidor AMQP em background

Na finalização do `lifespan`: fecha pool asyncpg e conexão RabbitMQ.

## Middlewares e segurança

| Middleware | Função |
|------------|--------|
| `SecurityHeadersMiddleware` | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `HSTS` |
| `SlowAPIMiddleware` | Rate limiting por IP (via SlowAPI) |
| `CORSMiddleware` | Origens permitidas via `ALLOWED_ORIGINS`; rejeita wildcard com credenciais |

## Variáveis de ambiente relevantes

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/arch_uploads` |
| `RABBITMQ_HOST/PORT/USER/PASSWORD` | Conexão ao broker |
| `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET` | Object storage |
| `JWT_SECRET_KEY` | Segredo de assinatura/verificação JWT (mín. 32 chars) |
| `ADMIN_USER/ADMIN_PASSWORD` | Credenciais do usuário padrão para `/token` |
| `ALLOWED_ORIGINS` | Origens CORS (separadas por vírgula) |
