# Report Service - Arquitetura Hexagonal

Servico de relatorios reestruturado seguindo os principios da Arquitetura Hexagonal (Ports & Adapters).

## Estrutura do Projeto

```
app/
├── domain/                      # Camada de Dominio (nucleo da aplicacao)
│   ├── __init__.py
│   ├── models.py                # Entidades de dominio (Report, ReportSummary, Feedback, Statistics)
│   └── exceptions.py            # Excecoes de dominio
│
├── application/                 # Camada de Aplicacao (casos de uso)
│   ├── __init__.py
│   ├── ports.py                 # Portas (interfaces) que a aplicacao precisa
│   └── report_management.py    # Casos de uso: GetReportUseCase, ListReportsUseCase, etc.
│
├── adapters/                    # Camada de Adaptadores
│   ├── inbound/                 # Adaptadores de entrada (HTTP)
│   │   ├── __init__.py
│   │   ├── http_routes.py       # Rotas FastAPI
│   │   └── schemas.py           # Schemas Pydantic para request/response
│   │
│   └── outbound/                # Adaptadores de saida (infraestrutura)
│       ├── __init__.py
│       └── asyncpg_reports.py   # Implementacao de ReportRepositoryPort e FeedbackRepositoryPort (PostgreSQL)
│
├── config.py                    # Configuracoes da aplicacao
├── bootstrap.py                 # Composicao de dependencias (Composition Root)
└── main.py                      # Entrypoint ASGI
```

## Principios da Arquitetura Hexagonal

### 1. **Domain (Dominio)**
- Nucleo da aplicacao, contem as regras de negocio
- Nao depende de nenhuma camada externa
- Define entidades e excecoes de dominio

### 2. **Application (Aplicacao)**
- Contem os casos de uso (use cases)
- Define as **portas** (interfaces) que precisa
- Orquestra o fluxo de negocio
- Nao conhece implementacoes concretas

### 3. **Adapters (Adaptadores)**
- **Inbound**: Recebem requisicoes externas (HTTP)
- **Outbound**: Implementam as portas definidas pela aplicacao (banco de dados)

### 4. **Bootstrap (Composicao)**
- Injeta as dependencias concretas nos casos de uso
- Configura a aplicacao e suas integracoes
- Unico lugar que conhece todas as implementacoes

## Fluxo de Dependencias

```
HTTP Request
    ↓
Inbound Adapter (http_routes.py)
    ↓
Use Case (report_management.py)
    ↓
Ports (interfaces)
    ↓
Outbound Adapter (asyncpg_reports.py)
    ↓
PostgreSQL
```

## Casos de Uso

- **GetReportUseCase**: Obter detalhes de um relatorio por upload ID
- **ListReportsUseCase**: Listar relatorios com filtro opcional de status
- **SubmitFeedbackUseCase**: Submeter feedback para um relatorio
- **GetStatisticsUseCase**: Obter estatisticas de uploads e feedback

## Beneficios desta Arquitetura

1. **Testabilidade**: Facil criar mocks das portas para testes unitarios
2. **Manutenibilidade**: Separacao clara de responsabilidades
3. **Flexibilidade**: Trocar implementacoes sem alterar o dominio
4. **Independencia**: Dominio nao depende de frameworks ou infraestrutura

## Como Executar

```bash
cd services/report-service
uvicorn app.main:app --host 0.0.0.0 --port 8004
```

## Endpoints

- `GET /health` - Health check
- `GET /health/db` - Database health check
- `GET /reports/{upload_id}` - Obter relatorio por ID
- `GET /reports` - Listar relatorios
- `POST /feedback` - Submeter feedback
- `GET /stats` - Obter estatisticas

## Variaveis de Ambiente

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
```
