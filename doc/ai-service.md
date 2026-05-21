# AI Service — arquitetura hexagonal

Descreve a organização interna do **AI Service** (`services/ai-service/`), seguindo o estilo **ports and adapters**. O núcleo da aplicação é independente de frameworks web, provedores de LLM, fila de mensagens e armazenamento.

## Princípios

- **Domínio** (`app/domain/`): entidades puras sem dependências externas.
- **Aplicação** (`app/application/`): define **portas** (interfaces `Protocol`) e **casos de uso** que orquestram o domínio.
- **Adaptadores** (`app/adapters/`):
  - **Inbound**: HTTP (FastAPI) e consumidor RabbitMQ.
  - **Outbound**: cliente LLM (OpenAI/OpenRouter), OCR multimodal, Tesseract, MinIO, publicador RabbitMQ.
- **Composição** (`app/bootstrap.py`): instancia adaptadores, injeta casos de uso e gerencia o ciclo de vida via `lifespan`.

> O AI Service **não possui banco de dados próprio**. O resultado da análise é publicado na fila `diagram.result` e cabe ao Upload Service persisti-lo.

## Estrutura de pastas

```
services/ai-service/
├── app/
│   ├── domain/
│   │   ├── models.py          # Component, Risk, AnalysisResult, DiagramTextExtraction
│   │   └── exceptions.py      # LlmAnalysisError, LlmNotConfiguredError
│   ├── application/
│   │   ├── ports.py           # LlmAnalyzerPort, TextExtractionPort, ResultPublisherPort
│   │   ├── analyze_diagram.py # AnalyzeDiagramUseCase
│   │   └── process_diagram_upload.py # ProcessDiagramUploadUseCase
│   ├── adapters/
│   │   ├── inbound/
│   │   │   ├── http_routes.py        # GET /health, POST /analyze
│   │   │   ├── rabbitmq_consumer.py  # Consome fila diagram.upload
│   │   │   └── schemas.py
│   │   └── outbound/
│   │       ├── openai_adapter.py            # OpenAiLlmAdapter (LlmAnalyzerPort)
│   │       ├── strands_multi_agents_adapter.py  # SwarmLlmAdapter (LlmAnalyzerPort)
│   │       ├── llm_ocr.py                   # LlmOCRAdapter (OCR multimodal Gemma)
│   │       ├── tesseract_ocr.py             # TesseractTextExtractor (fallback)
│   │       ├── minio_storage.py             # MinIOStorage
│   │       ├── rabbitmq_result_publisher.py # RabbitMQResultPublisher (ResultPublisherPort)
│   │       └── llm_json_parser.py           # Parser/validador do JSON da IA
│   ├── config.py       # Settings (Pydantic) carregado de variáveis de ambiente
│   ├── bootstrap.py    # Wiring de dependências e lifespan do FastAPI
│   └── main.py         # ASGI app (uvicorn app.main:app)
├── tests/
│   ├── unit/           # Testes unitários (sem chamadas reais ao LLM)
│   └── ragas_eval/     # Avaliação comportamental com Ragas (manual, com custo de API)
├── requirements.txt
└── Dockerfile
```

## Portas (interfaces)

Definidas em `app/application/ports.py`:

| Porta | Papel |
|-------|-------|
| `LlmAnalyzerPort` | Recebe texto extraído do diagrama e retorna `AnalysisResult` (components, risks, summary). |
| `TextExtractionPort` | Dado um caminho de arquivo, retorna o texto extraído (interface do Tesseract). |
| `ResultPublisherPort` | Publica eventos de resultado na fila `diagram.result` (PROCESSING, DONE, ERROR). |

## Casos de uso

### `AnalyzeDiagramUseCase`

Usado pelo endpoint HTTP `POST /analyze`. Recebe texto diretamente e retorna análise. Útil para testes sem passar pela fila.

```
POST /analyze (texto) → LlmAnalyzerPort.analyze() → AnalysisResult
```

### `ProcessDiagramUploadUseCase`

Disparado pelo consumidor RabbitMQ. Fluxo completo:

```
diagram.upload recebida
    │
    ├─ publisher.publish_processing(upload_id)          → diagram.result {PROCESSING}
    │
    ├─ [se minio://] storage.download_file(file_path)   → arquivo local temporário
    │
    ├─ _validate_file()  extensão + tamanho (max 50 MB) + MIME real (python-magic)
    │
    ├─ ocr.analyze_diagram(local_path)                  → DiagramTextExtraction
    │     ├─ Tentativa 1: LlmOCRAdapter (Gemma 4 26B multimodal)
    │     └─ Fallback: TesseractTextExtractor
    │
    ├─ llm.analyze(texto, source_hint)                  → AnalysisResult (Strands swarm)
    │
    ├─ publisher.publish_done(upload_id, payload_json)  → diagram.result {DONE}
    │
    └─ [erro] publisher.publish_failed(upload_id, msg)  → diagram.result {ERROR}
```

O `payload_json` contém:
```json
{
  "text": "...",
  "text_extraction": { "source": "llm_multimodal|tesseract", "multimodal_model": "...", "detail_pt": "..." },
  "ai": { "components": [...], "risks": [...], "summary": "...", "source_assessment": "..." }
}
```

## Adaptadores outbound

### OCR — `LlmOCRAdapter`

Extrai texto de imagens e PDFs usando um modelo LLM multimodal (configurado em `LLM_OCR`, padrão `google/gemma-4-26b-a4b-it`). Para PDFs converte páginas em imagens antes de enviar ao modelo. Fallback automático para `TesseractTextExtractor` se o LLM OCR estiver desabilitado (`LLM_OCR_DISABLE=1`) ou falhar.

Limites configuráveis via env:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `LLM_OCR_MAX_PDF_PAGES` | `15` | Páginas máximas de PDF a processar |
| `LLM_OCR_MAX_TOKENS` | `4096` | Tokens máximos na resposta OCR |
| `LLM_OCR_IMAGE_MAX_SIDE` | `2048` | Resolução máxima da imagem |
| `LLM_OCR_DISABLE` | `false` | Força uso do Tesseract |

### LLM — `SwarmLlmAdapter` (Strands)

Implementa `LlmAnalyzerPort` com um swarm de agentes Strands (framework AWS). Três agentes especializados analisam o diagrama em paralelo/sequência e consolidam o resultado:

- **Agente de arquitetura**: componentes, padrões e camadas
- **Agente de infraestrutura**: infraestrutura, deploy e operações
- **Agente de desenvolvimento**: boas práticas, qualidade e segurança

Parâmetros configuráveis: `MAX_HANDOFFS`, `MAX_ITERATIONS`, `EXECUTION_TIMEOUT`, `NODE_TIMEOUT`, `REPETITIVE_HANDOFF_DETECTION_WINDOW`.

### LLM — `OpenAiLlmAdapter`

Implementação alternativa de `LlmAnalyzerPort` usando o SDK OpenAI diretamente (sem swarm). Usado no endpoint `POST /analyze` para testes pontuais.

### Publicador — `RabbitMQResultPublisher`

Implementa `ResultPublisherPort`. Publica na fila `diagram.result` (durable) com `DeliveryMode.PERSISTENT`. Três métodos:

- `publish_processing(upload_id)` → `{upload_id, status: "PROCESSING"}`
- `publish_done(upload_id, payload_json)` → `{upload_id, status: "DONE", payload_json}`
- `publish_failed(upload_id, error_message)` → `{upload_id, status: "ERROR", error_message}`

## Adaptadores inbound

### HTTP — `http_routes.py`

| Rota | Auth | Descrição |
|------|------|-----------|
| `GET /health` | — | Liveness check |
| `POST /analyze` | JWT | Análise direta por texto (sem fila) |

### RabbitMQ — `rabbitmq_consumer.py`

Declara a fila `diagram.upload` (durable, prefetch=1) e encaminha cada mensagem ao `ProcessDiagramUploadUseCase`. A mensagem deve conter: `upload_id`, `filename`, `file_path`, `content_type`.

## Segurança e middlewares

| Middleware | Função |
|-----------|--------|
| `SecurityHeadersMiddleware` | X-Content-Type-Options, X-Frame-Options, HSTS |
| `RequestSizeLimitMiddleware` | Rejeita requests > 50 MB (413) |
| `SlowAPIMiddleware` | Rate limiting por IP |
| `CORSMiddleware` | Restringe origens via `ALLOWED_ORIGINS`; `allow_credentials=False` |

## Configuração relevante

| Variável | Descrição |
|----------|-----------|
| `OPENAI_API_KEY` | Chave do provedor LLM (OpenRouter em produção) |
| `OPENAI_BASE_URL` | URL base do provedor (padrão: `https://openrouter.ai/api/v1`) |
| `LLM_MODEL` | Modelo para análise swarm (padrão: `deepseek/deepseek-v3.2`) |
| `LLM_OCR` | Modelo para OCR multimodal (padrão: `google/gemma-4-26b-a4b-it`) |
| `RABBITMQ_*` | Host, porta, usuário, senha |
| `MINIO_*` | Endpoint, credenciais, bucket |
| `JWT_SECRET_KEY` | Deve coincidir com o do Upload Service |

## Docker

A imagem instala dependências de sistema para OCR (Tesseract, Poppler para PDF) e executa `uvicorn app.main:app` na porta **8003**. Contexto de build: `services/ai-service/`.
