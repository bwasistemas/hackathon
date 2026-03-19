Você é um engenheiro DevOps/SRE sênior especializado em Docker, observabilidade e CI/CD para microsserviços Python.

## CONTEXTO

Estou construindo um MVP de análise automatizada de diagramas de arquitetura de software para um hackathon acadêmico. O sistema usa microsserviços Python (FastAPI) com RabbitMQ para mensageria assíncrona.

### O que JÁ TENHO rodando via Docker Compose:
- RabbitMQ (com management plugin, porta 15672)
- Prometheus
- Grafana

### Serviços que PRECISO orquestrar (todos Python/FastAPI):
1. **upload-service** - Recebe diagramas (imagem/PDF) via REST, publica na fila RabbitMQ
2. **processing-worker** - Consome da fila, faz OCR/parsing, chama o AI service
3. **ai-service** - Recebe texto extraído, retorna análise JSON via LLM (OpenAI-compatible API)
4. **report-service** - Persiste e serve relatórios via REST

### Infraestrutura adicional necessária:
- PostgreSQL (cada serviço que precisa de persistência tem schema próprio ou DB próprio)
- Rede Docker compartilhada entre todos os serviços

## O QUE PRECISO QUE VOCÊ GERE

### 1. Docker Compose COMPLETO (docker-compose.yml)
- Integrar os serviços acima com o RabbitMQ, Prometheus e Grafana que já tenho
- PostgreSQL com healthcheck
- Variáveis de ambiente via .env (não hardcode)
- Dependências (depends_on com condition: service_healthy)
- Volumes nomeados para dados persistentes
- Uma única rede bridge para todos os serviços
- Restart policies adequadas

### 2. Dockerfile para cada serviço Python
- Multi-stage build (builder + runtime)
- Imagem base: python:3.12-slim
- Instalar dependências de sistema para OCR no processing-worker (tesseract-ocr, poppler-utils)
- Usuário não-root
- HEALTHCHECK em cada container

### 3. Prometheus - configuração de scraping
- prometheus.yml configurado para coletar métricas de todos os serviços FastAPI
- Os serviços vão expor métricas via prometheus-fastapi-instrumentator na rota /metrics
- Incluir scrape do RabbitMQ (rabbitmq_exporter ou plugin prometheus nativo)

### 4. Grafana - dashboards provisionados
- Provisioning via arquivos YAML (datasource Prometheus automático)
- 1 dashboard JSON básico com:
  - Request rate por serviço
  - Latência p95 por endpoint
  - Fila RabbitMQ: mensagens pendentes, taxa de consumo
  - Status dos serviços (up/down)

### 5. Pipeline CI/CD (GitHub Actions)
- Arquivo .github/workflows/ci.yml
- Jobs:
  - Lint (ruff ou flake8)
  - Testes unitários (pytest) por serviço
  - Build das imagens Docker
  - Push para registry (pode ser ghcr.io)
  - Deploy local via docker-compose (ou indicar como adaptar para cloud)

### 6. Arquivo .env.example
- Todas as variáveis de ambiente com valores padrão para dev local
- Separar claramente: DB, RabbitMQ, AI/LLM, MinIO (se usar), Grafana

### 7. Estrutura de pastas esperada (só a parte de infra)
```
infrastructure/
├── docker-compose.yml
├── .env.example
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml
│   │   └── dashboards/
│   │       ├── dashboard.yml
│   │       └── overview.json
│   └── grafana.ini (opcional)
├── dockerfiles/
│   ├── Dockerfile.upload
│   ├── Dockerfile.processing
│   ├── Dockerfile.ai
│   └── Dockerfile.report
└── .github/
    └── workflows/
        └── ci.yml
```

## REQUISITOS DE SEGURANÇA (OBRIGATÓRIO)
- Serviços NÃO rodam como root
- Variáveis sensíveis (API keys, DB passwords) via .env, nunca no código
- RabbitMQ com credenciais configuráveis (não guest/guest em produção)
- PostgreSQL com senha forte configurável
- Rede interna Docker isolada (serviços não expõem portas desnecessárias ao host)
- Healthchecks em todos os serviços críticos

## REGRAS
- Gere código REAL e funcional, não pseudocódigo
- Use boas práticas Docker (camadas otimizadas, .dockerignore)
- Tudo deve funcionar com `docker-compose up -d` a partir do zero
- Comente apenas o necessário, priorize código limpo
- Se a resposta ficar grande, divida em partes e me avise

Comece pelo docker-compose.yml completo + Dockerfiles + prometheus.yml.