# Arch Analyzer - Infrastructure

Este diretório contém toda a infraestrutura Docker e configurações de observabilidade para o sistema de análise automatizada de diagramas de arquitetura.

## Estrutura

```
infrastructure/
├── docker-compose.yml          # Orquestração de todos os serviços
├── .env.example                # Template de variáveis de ambiente
├── dockerignore                # Arquivos ignorados no build Docker
├── prometheus/
│   └── prometheus.yml          # Configuração do Prometheus
├── grafana/
│   ├── grafana.ini             # Configuração do Grafana
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml  # Datasource automático
│       └── dashboards/
│           ├── dashboard.yml   # Provider de dashboards
│           └── overview.json   # Dashboard principal
├── dockerfiles/
│   ├── Dockerfile.upload       # Upload Service
│   ├── Dockerfile.processing   # Processing Worker
│   ├── Dockerfile.ai           # AI Service
│   └── Dockerfile.report      # Report Service
└── .github/
    └── workflows/
        └── ci.yml             # Pipeline CI/CD
```

## Quick Start

1. **Configurar variáveis de ambiente:**
   ```bash
   cp .env.example .env
   # Edite o .env com suas credenciais
   ```

2. **Subir todos os serviços:**
   ```bash
   docker-compose up -d
   ```

3. **Verificar status:**
   ```bash
   docker-compose ps
   ```

## Serviços e Portas

| Serviço | Porta | Descrição |
|---------|-------|-----------|
| upload-service | 8001 | Recebe diagramas via REST |
| processing-worker | 8002 | Processamento OCR/parsing |
| ai-service | 8003 | Análise via LLM |
| report-service | 8004 | Servir relatórios |
| rabbitmq | 5672/15672 | Message broker + UI |
| postgres | 5432 | Banco de dados |
| prometheus | 9090 | Coleta de métricas |
| grafana | 3000 | Dashboards |

## Endpoints

- **Upload Service:** http://localhost:8001/docs
- **AI Service:** http://localhost:8003/docs
- **Report Service:** http://localhost:8004/docs
- **RabbitMQ UI:** http://localhost:15672
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/changeme_secure_password)

## Variáveis de Ambiente

### Banco de Dados
- `POSTGRES_USER` - Usuário do banco
- `POSTGRES_PASSWORD` - Senha do banco
- `POSTGRES_DB` - Nome do banco

### RabbitMQ
- `RABBITMQ_USER` - Usuário do RabbitMQ
- `RABBITMQ_PASSWORD` - Senha do RabbitMQ

### AI/LLM
- `OPENAI_API_KEY` - Chave da API OpenAI
- `OPENAI_BASE_URL` - URL base da API
- `LLM_MODEL` - Modelo LLM a ser usado

### Grafana
- `GRAFANA_USER` - Usuário admin
- `GRAFANA_PASSWORD` - Senha admin

## CI/CD

O pipeline está configurado no GitHub Actions e inclui:
- Lint (ruff, black)
- Testes unitários por serviço
- Build de imagens Docker
- Deploy automático para branch develop

## Volumes Persistentes

- `postgres_data` - Dados do PostgreSQL
- `rabbitmq_data` - Dados do RabbitMQ
- `grafana_data` - Dados e dashboards do Grafana
- `uploads_data` - Arquivos enviados
- `prometheus_data` - Métricas do Prometheus

## Segurança

- Todos os serviços rodam como usuário não-root
- Credenciais via variáveis de ambiente
- Rede Docker isolada (`arch-analyzer-net`)
- Healthchecks em todos os serviços críticos