# Comparação: Estrutura Antiga vs. Nova (Arquitetura Hexagonal)

## Estrutura Antiga (Monolítica)

```
upload-service/
├── main.py                 # Tudo em um único arquivo:
│                           # - Configurações
│                           # - Lógica de negócio
│                           # - Integração com DB, MinIO, RabbitMQ
│                           # - Rotas HTTP
├── requirements.txt
└── Dockerfile
```

**Problemas:**
- Código acoplado e difícil de testar
- Lógica de negócio misturada com infraestrutura
- Difícil de manter e evoluir
- Impossível trocar implementações

---

## Nova Estrutura (Arquitetura Hexagonal)

```
upload-service/
├── app/
│   ├── domain/                      # NÚCLEO - Regras de Negócio
│   │   ├── models.py                # Entidades: Upload, UploadResult
│   │   └── exceptions.py            # Exceções de domínio
│   │
│   ├── application/                 # CASOS DE USO
│   │   ├── ports.py                 # Interfaces (contratos)
│   │   └── upload_file.py           # UploadFileUseCase, ListUploadsUseCase
│   │
│   ├── adapters/
│   │   ├── inbound/                 # ENTRADA - HTTP
│   │   │   ├── http_routes.py       # Rotas FastAPI
│   │   │   └── schemas.py           # DTOs HTTP
│   │   │
│   │   └── outbound/                # SAÍDA - Infraestrutura
│   │       ├── minio_storage.py     # MinIO
│   │       ├── asyncpg_uploads.py   # PostgreSQL
│   │       └── rabbitmq_publisher.py # RabbitMQ
│   │
│   ├── config.py                    # Configurações
│   ├── bootstrap.py                 # Injeção de Dependências
│   └── main.py                      # Entrypoint
│
├── main.py (LEGADO - pode ser removido)
├── requirements.txt
├── Dockerfile
└── README.md
```

## Camadas e Responsabilidades

### 1. Domain (Domínio) - Núcleo da Aplicação
**O que é:** Regras de negócio puras, sem dependências externas

**Arquivos:**
- `models.py`: Entidades de domínio (Upload, UploadResult)
- `exceptions.py`: Exceções específicas do domínio

**Características:**
- ✅ Não importa nada de infraestrutura
- ✅ Não conhece FastAPI, PostgreSQL, MinIO
- ✅ Apenas regras de negócio

### 2. Application (Aplicação) - Casos de Uso
**O que é:** Orquestração da lógica de negócio

**Arquivos:**
- `ports.py`: Interfaces (contratos) que a aplicação precisa
  - `StoragePort`: Interface para armazenamento
  - `UploadRepositoryPort`: Interface para persistência
  - `MessagePublisherPort`: Interface para mensageria
- `upload_file.py`: Implementação dos casos de uso

**Características:**
- ✅ Define INTERFACES (portas), não implementações
- ✅ Depende apenas do domínio
- ✅ Testável com mocks

### 3. Adapters (Adaptadores) - Implementações Concretas

#### Inbound (Entrada) - HTTP
**O que é:** Recebe requisições externas e traduz para o domínio

**Arquivos:**
- `http_routes.py`: Rotas FastAPI
- `schemas.py`: DTOs Pydantic

**Responsabilidades:**
- Receber requisições HTTP
- Validar entrada
- Chamar casos de uso
- Converter exceções em HTTP status codes

#### Outbound (Saída) - Infraestrutura
**O que é:** Implementa as portas definidas pela aplicação

**Arquivos:**
- `minio_storage.py`: Implementa `StoragePort`
- `asyncpg_uploads.py`: Implementa `UploadRepositoryPort`
- `rabbitmq_publisher.py`: Implementa `MessagePublisherPort`

**Responsabilidades:**
- Comunicação com MinIO
- Persistência no PostgreSQL
- Publicação de eventos no RabbitMQ

### 4. Composition Root (Raiz de Composição)

**Arquivos:**
- `config.py`: Carrega configurações do ambiente
- `bootstrap.py`: Conecta todas as peças (dependency injection)
- `main.py`: Entrypoint ASGI

**Responsabilidades:**
- Criar instâncias dos adaptadores
- Injetar dependências nos casos de uso
- Configurar o FastAPI

## Fluxo de uma Requisição

```
1. HTTP POST /upload
   ↓
2. http_routes.py (Inbound Adapter)
   ↓
3. UploadFileUseCase (Application)
   ↓
4. Portas (Interfaces):
   - StoragePort.upload_file()
   - UploadRepositoryPort.create_upload()
   - MessagePublisherPort.publish_upload_event()
   ↓
5. Outbound Adapters:
   - MinIOStorageAdapter
   - AsyncpgUploadRepository
   - RabbitMQPublisher
   ↓
6. External Systems:
   - MinIO
   - PostgreSQL
   - RabbitMQ
```

## Vantagens da Nova Arquitetura

### 1. Testabilidade
Antes:
```python
# Impossível testar sem banco de dados real
async def test_upload():
    # Precisa de PostgreSQL, MinIO, RabbitMQ rodando
    ...
```

Depois:
```python
# Testes unitários com mocks
async def test_upload():
    mock_storage = MockStorage()
    mock_repo = MockRepository()
    mock_publisher = MockPublisher()
    
    use_case = UploadFileUseCase(mock_storage, mock_repo, mock_publisher)
    result = await use_case.execute("test.png", b"content", "image/png")
    
    assert result.status == "RECEIVED"
```

### 2. Flexibilidade
Trocar implementações sem alterar o core:
- MinIO → AWS S3: apenas criar novo adaptador
- PostgreSQL → MongoDB: apenas implementar nova UploadRepositoryPort
- RabbitMQ → Kafka: apenas implementar nova MessagePublisherPort

### 3. Clareza
Cada camada tem responsabilidade única e bem definida

### 4. Manutenibilidade
Código organizado e fácil de navegar

## Comparação com ai-service

A estrutura segue o mesmo padrão do `ai-service`:

| Aspecto | upload-service | ai-service |
|---------|---------------|------------|
| Domain | Upload, UploadResult | Component, Risk, AnalysisResult |
| Ports | StoragePort, UploadRepositoryPort, MessagePublisherPort | LlmAnalyzerPort, TextExtractionPort, UploadRepositoryPort |
| Inbound | HTTP (FastAPI) | HTTP (FastAPI) + RabbitMQ Consumer |
| Outbound | MinIO, PostgreSQL, RabbitMQ | MinIO, PostgreSQL, OpenAI, Tesseract |
| Bootstrap | Dependency Injection | Dependency Injection |

## Próximos Passos (Opcional)

1. Remover o arquivo `main.py` legado da raiz
2. Adicionar testes unitários para casos de uso
3. Adicionar testes de integração
4. Adicionar validação de tipos de arquivo
5. Implementar retry logic para falhas de infraestrutura
