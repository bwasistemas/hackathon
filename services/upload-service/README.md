# Upload Service - Arquitetura Hexagonal

Serviço de upload de arquivos reestruturado seguindo os princípios da Arquitetura Hexagonal (Ports & Adapters).

## Estrutura do Projeto

```
app/
├── domain/                      # Camada de Domínio (núcleo da aplicação)
│   ├── __init__.py
│   ├── models.py                # Entidades de domínio (Upload, UploadResult)
│   └── exceptions.py            # Exceções de domínio
│
├── application/                 # Camada de Aplicação (casos de uso)
│   ├── __init__.py
│   ├── ports.py                 # Portas (interfaces) que a aplicação precisa
│   └── upload_file.py           # Casos de uso: UploadFileUseCase, ListUploadsUseCase, GetUploadUseCase
│
├── adapters/                    # Camada de Adaptadores
│   ├── inbound/                 # Adaptadores de entrada (HTTP)
│   │   ├── __init__.py
│   │   ├── http_routes.py       # Rotas FastAPI
│   │   └── schemas.py           # Schemas Pydantic para request/response
│   │
│   └── outbound/                # Adaptadores de saída (infraestrutura)
│       ├── __init__.py
│       ├── minio_storage.py     # Implementação de StoragePort (MinIO)
│       ├── asyncpg_uploads.py   # Implementação de UploadRepositoryPort (PostgreSQL)
│       └── rabbitmq_publisher.py # Implementação de MessagePublisherPort (RabbitMQ)
│
├── config.py                    # Configurações da aplicação
├── bootstrap.py                 # Composição de dependências (Composition Root)
└── main.py                      # Entrypoint ASGI
```

## Princípios da Arquitetura Hexagonal

### 1. **Domain (Domínio)**
- Núcleo da aplicação, contém as regras de negócio
- Não depende de nenhuma camada externa
- Define entidades e exceções de domínio

### 2. **Application (Aplicação)**
- Contém os casos de uso (use cases)
- Define as **portas** (interfaces) que precisa
- Orquestra o fluxo de negócio
- Não conhece implementações concretas

### 3. **Adapters (Adaptadores)**
- **Inbound**: Recebem requisições externas (HTTP, mensagens, CLI, etc.)
- **Outbound**: Implementam as portas definidas pela aplicação (banco de dados, storage, filas, APIs externas)

### 4. **Bootstrap (Composição)**
- Injeta as dependências concretas nos casos de uso
- Configura a aplicação e suas integrações
- Único lugar que conhece todas as implementações

## Fluxo de Dependências

```
HTTP Request
    ↓
Inbound Adapter (http_routes.py)
    ↓
Use Case (upload_file.py)
    ↓
Ports (interfaces)
    ↓
Outbound Adapters (minio_storage.py, asyncpg_uploads.py, rabbitmq_publisher.py)
    ↓
External Systems (MinIO, PostgreSQL, RabbitMQ)
```

## Benefícios desta Arquitetura

1. **Testabilidade**: Fácil criar mocks das portas para testes unitários
2. **Manutenibilidade**: Separação clara de responsabilidades
3. **Flexibilidade**: Trocar implementações sem alterar o domínio
4. **Independência**: Domínio não depende de frameworks ou infraestrutura
5. **Escalabilidade**: Fácil adicionar novos adaptadores

## Como Executar

```bash
cd services/upload-service
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Endpoints

- `POST /upload` - Upload de arquivo
- `GET /uploads` - Listar uploads
- `GET /uploads/{upload_id}` - Detalhes de um upload
- `GET /health` - Health check

## Variáveis de Ambiente

Veja o arquivo `.env.example` para configurações disponíveis.
