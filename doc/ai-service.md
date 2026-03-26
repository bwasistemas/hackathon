# AI Service — arquitetura hexagonal

Este documento descreve a organização interna do **AI Service** (`services/ai-service/`), refatorado segundo o estilo **ports and adapters** (arquitetura hexagonal). O objetivo é manter o núcleo da aplicação independente de frameworks web, de provedores de LLM e de tecnologias de fila e banco.

## Princípios

- **Domínio** (`app/domain/`): entidades e modelos de resultado da análise; não importa FastAPI, OpenAI, asyncpg nem RabbitMQ.
- **Aplicação** (`app/application/`): define **portas** (interfaces) e **casos de uso** que orquestram o domínio. Depende apenas do domínio e das abstrações (ports).
- **Adaptadores** (`app/adapters/`):
  - **Inbound**: entradas do sistema — HTTP (FastAPI) e consumidor RabbitMQ.
  - **Outbound**: saídas para sistemas externos — cliente LLM, repositório PostgreSQL (asyncpg), OCR (Tesseract / Pillow / pdf2image).

- **Composição** (`app/bootstrap.py`): lê configuração, instancia adaptadores concretos, injeta os casos de uso e registra o ciclo de vida da aplicação (pool do banco, conexão RabbitMQ).

- **Entrada ASGI** (`app/main.py`): expõe `app` para o Uvicorn (`uvicorn app.main:app`).

## Estrutura de pastas

```
services/ai-service/
├── app/
│   ├── domain/              # Modelos e exceções de domínio
│   ├── application/       # Portas (protocolos) e casos de uso
│   ├── adapters/
│   │   ├── inbound/         # Rotas HTTP, schemas Pydantic, RabbitMQ
│   │   └── outbound/        # OpenAI, asyncpg, OCR
│   ├── config.py            # Configuração a partir de variáveis de ambiente
│   ├── bootstrap.py         # Montagem do FastAPI e wiring
│   └── main.py              # ASGI app
├── requirements.txt
└── Dockerfile
```

## Portas (interfaces)

Definidas em `app/application/ports.py`, em termos de responsabilidade:

| Porta | Papel |
|-------|--------|
| `LlmAnalyzerPort` | Recebe texto extraído do diagrama e devolve um `AnalysisResult` (componentes, riscos, resumo). |
| `TextExtractionPort` | Dado um caminho de arquivo no disco, devolve texto (OCR ou leitura de PDF). |
| `UploadRepositoryPort` | Atualiza status do upload e persiste o payload final da análise no banco. |

Implementações concretas ficam em `app/adapters/outbound/`.

## Casos de uso

- **`AnalyzeDiagramUseCase`**: usa apenas `LlmAnalyzerPort`. É o núcleo do endpoint HTTP `POST /analyze`, que permite testar a análise enviando texto diretamente, sem passar pela fila.
- **`ProcessDiagramUploadUseCase`**: usa `TextExtractionPort`, `LlmAnalyzerPort` e `UploadRepositoryPort`. É o fluxo disparado pelo **RabbitMQ** após um upload: OCR → LLM → persistência.

## Adaptadores outbound

- **OpenAI (`OpenAiLlmAdapter`)**: implementa `LlmAnalyzerPort` com o SDK OpenAI; usa `asyncio.to_thread` para não bloquear o loop de eventos nas chamadas síncronas. Se não houver chave de API, o domínio sinaliza indisponibilidade (`LlmNotConfiguredError`).
- **PostgreSQL (`AsyncpgUploadRepository`)**: implementa `UploadRepositoryPort` com pool asyncpg. Se o banco não estiver disponível na subida, pode ser usado um **repositório nulo** (`NullUploadRepository`) que não falha o processamento mas não persiste dados.
- **OCR (`TesseractTextExtractor`)**: implementa `TextExtractionPort` com Pillow, pytesseract e, para PDF, pdf2image + Poppler.

## Adaptadores inbound

- **HTTP**: rotas em `app/adapters/inbound/http_routes.py`; schemas de request/response em `schemas.py`. O caso de uso de análise é obtido via `app.state` após o startup (lifespan).
- **RabbitMQ**: `connect_rabbitmq` e `start_diagram_upload_consumer` declaram a fila (por exemplo `diagram.upload`) e encaminham cada mensagem ao `ProcessDiagramUploadUseCase`.

## Configuração relevante

Variáveis típicas: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `DATABASE_URL`, `RABBITMQ_*`. A centralização está em `app/config.py` (`Settings`).

## Docker

A imagem instala dependências de sistema necessárias para OCR (por exemplo Tesseract e Poppler) e executa `uvicorn app.main:app` na porta **8003**. Para builds de CI que usam `infrastructure/dockerfiles/Dockerfile.ai`, o contexto de build esperado é o diretório `services/ai-service` (contendo `requirements.txt` e a pasta `app/`).
