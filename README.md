# Arch Analyzer

MVP para análise automatizada de diagramas de arquitetura de software (imagens ou PDF), com microsserviços, mensageria, dois bancos de dados dedicados por serviço, observabilidade e pipeline de IA integrado ao fluxo real de upload.

**Repositório:** [github.com/bwasistemas/hackathon](https://github.com/bwasistemas/hackathon)
MVP: https://archanalyzer.brunoretiro.com.br/  


---

## Contexto e objetivo

O desafio do hackathon integrado (IA para Devs + Software Architecture) propõe um MVP capaz de:

1. Receber diagramas de arquitetura (imagem ou PDF).
2. Processar o diagrama de forma assíncrona.
3. Aplicar IA para análise automática.
4. Gerar um relatório técnico estruturado.
5. Permitir consulta do status e do resultado pelo usuário.

O **Arch Analyzer** executa esse ciclo com arquitetura distribuída: upload, fila RabbitMQ, processamento no AI Service, persistência em PostgreSQL/MinIO e consulta via Report Service.

Documentação complementar em [`doc/`](doc/README.md).

---

## Arquitetura

```text
  Analista
     │ HTTPS
     ▼
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (Nginx :8051)                                          │
│  SPA estática · proxy /upload-service/ /report-service/ /ai-service/ │
└────────┬──────────────────────┬───────────────────────┬──────────┘
         │ HTTP+JWT              │ HTTP+JWT               │ HTTP
         ▼                       ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Upload Service │    │  Report Service  │    │   AI Service     │
│  FastAPI :8001  │    │  FastAPI :8004   │    │   FastAPI :8003  │
│                 │    │                  │    │  (sem banco)     │
│  Publica:       │◀───│  GET /uploads    │    │  KEDA autoscale  │
│  diagram.upload │    │  GET /stats      │    └────────┬─────────┘
│                 │    │  (JWT s2s)       │             │ AMQP
│  Consome:       │    └────────┬─────────┘             │
│  diagram.result │             │ asyncpg               ▼
└────────┬────────┘             ▼              ┌──────────────────┐
         │ asyncpg     ┌──────────────┐        │    RabbitMQ      │
         ▼             │ arch_reports │        │    :5672         │
┌──────────────┐       │ PostgreSQL   │        │                  │
│ arch_uploads │       │ (feedback)   │        │ diagram.upload ──┼──▶ AI Service
│ PostgreSQL   │       └──────────────┘        │ diagram.result ◀─┼─── AI Service
│ (uploads +   │                               └──────────────────┘
│  users)      │                                        │
└──────────────┘       ┌──────────────────────┐         │
         ▲             │        MinIO          │◀────────┘ S3 API
         │             │  Object Store :9000   │
         └─────────────│  (arquivos de upload) │
           PUT/result  └──────────────────────┘
```

```text
Observabilidade:

┌──────────────┐  scrape  ┌──────────────┐  datasource  ┌──────────────┐
│  Prometheus  │─────────▶│    Grafana   │◀─────────────│     Loki     │
│   :9090      │          │    :3000     │              │    :3100     │
└──────────────┘          └──────────────┘              └──────▲───────┘
                                                               │ push logs
                                                        ┌──────┴───────┐
                                                        │   Promtail   │
                                                        └──────────────┘
```

| Componente | Responsabilidade |
|------------|------------------|
| **Frontend** | SPA estática (Nginx): upload, acompanhamento de status, relatórios e feedback. Proxy reverso para as APIs na mesma origem. Login JWT. |
| **Upload Service** | Recebe arquivo, valida tamanho/tipo, grava no MinIO, persiste metadados em `arch_uploads`, publica `diagram.upload` e consome `diagram.result` para atualizar o status. Emite tokens JWT. |
| **RabbitMQ** | Desacopla upload do processamento de IA. Fila `diagram.upload` (upload→ai) e `diagram.result` (ai→upload). |
| **AI Service** | Consome `diagram.upload`, executa OCR multimodal (Gemma 4 26B) com fallback Tesseract, analisa com swarm Strands (DeepSeek v3.2) e publica o resultado em `diagram.result`. **Sem acesso direto a banco de dados.** |
| **Report Service** | Serve relatórios e coleta feedback. Lê dados de uploads via **HTTP do Upload Service** (JWT service-to-service). Persiste avaliações em `arch_reports`. |
| **PostgreSQL** | Dois bancos dedicados: `arch_uploads` (dono: Upload Service) e `arch_reports` (dono: Report Service). |
| **MinIO** | Object storage S3-compatible dos arquivos enviados. |
| **Prometheus / Grafana / Loki / Promtail** | Métricas HTTP, dashboards e logs estruturados dos containers. |

Cada serviço FastAPI segue **arquitetura hexagonal** (domínio, aplicação, portas e adaptadores).

| Documento técnico | Conteúdo |
| --- | --- |
| [`doc/upload-service.md`](doc/upload-service.md) | Casos de uso, adaptadores asyncpg/MinIO/RabbitMQ, consumidor AMQP e ciclo de status |
| [`doc/ai-service.md`](doc/ai-service.md) | OCR multimodal, swarm Strands/DeepSeek, portas e adaptadores |
| [`doc/report-service.md`](doc/report-service.md) | HttpUploadClientAdapter (s2s JWT), feedback, estatísticas e bootstrap |
| [`doc/aplicacao.md`](doc/aplicacao.md) | Visão geral: fluxos, portas, filas, bancos e configuração |
| [`doc/c4-arch-analyzer-clean.dsl`](doc/c4-arch-analyzer-clean.dsl) | Diagrama C4 (Structurizr DSL): contexto, containers, fluxos e deploy |

---

## Fluxo principal

1. O usuário envia PNG, JPG, JPEG ou PDF pelo frontend.
2. O **Upload Service** aplica limite de **10 MB**, salva no MinIO e cria registro em `arch_uploads` com status `RECEIVED`.
3. O Upload Service publica `diagram.upload` no RabbitMQ (`upload_id`, `filename`, `file_path`, `content_type`).
4. O **AI Service** consome a mensagem e publica `diagram.result {status: PROCESSING}`; o Upload Service recebe e atualiza o banco.
5. O AI Service baixa o arquivo do MinIO, executa OCR multimodal (Gemma 4 26B) com fallback Tesseract e analisa com swarm Strands (DeepSeek v3.2).
6. O resultado (`components`, `risks`, `summary`) é publicado em `diagram.result {status: DONE, payload_json}`; o Upload Service grava o payload em `arch_uploads`.
7. O **Report Service** serve o relatório lendo o Upload Service via HTTP. O usuário pode enviar feedback (1–5 estrelas) persistido em `arch_reports`.

Estados do upload: `RECEIVED` → `PROCESSING` → `DONE` | `ERROR`.

---

## Estrutura do projeto

```
hackathon/
├── frontend/                 # SPA estática (HTML/JS/CSS) + Nginx
├── services/
│   ├── upload-service/       # Upload, MinIO, filas diagram.upload/result, JWT
│   ├── ai-service/           # Consumer RabbitMQ, OCR/LLM Strands, sem banco próprio
│   └── report-service/       # Relatórios via HTTP s2s, feedback em arch_reports
├── infrastructure/
│   ├── docker-compose.yml    # Stack local (inclui postgres-setup idempotente)
│   ├── docker-compose.prod.yml
│   ├── k8s/                  # Manifests Kubernetes (deploy na VPS via Kind)
│   ├── k8s-geral/            # Observabilidade no namespace arch-geral
│   ├── postgres/             # init-databases.sh (fresh deploy)
│   ├── prometheus/ grafana/ loki/ promtail/ rabbitmq/
│   └── .env.example
├── .github/workflows/        # Testes e deploy (GitHub Actions)
├── .vps/                     # Scripts de setup inicial da VPS
├── doc/                      # Documentação técnica + diagramas C4
├── scripts/
│   └── security-check.sh     # Validação de configurações de segurança
├── setup.sh                  # Sobe o ambiente local (Linux/macOS)
├── wsl-setup.sh              # Equivalente ao setup.sh para WSL
└── README.md
```

---

## Quick Start

### 1. Clone e configure

```bash
git clone https://github.com/bwasistemas/hackathon.git
cd hackathon

cp infrastructure/.env.example infrastructure/.env
# Edite infrastructure/.env (JWT, LLM, credenciais)
```

Gere um `JWT_SECRET_KEY` seguro (obrigatório):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Suba os serviços

```bash
# Opção recomendada
chmod +x setup.sh && ./setup.sh

# Ou manualmente
cd infrastructure && docker compose up -d
```

Comandos do `setup.sh`: `start` (padrão), `stop`, `restart`, `logs`, `status`, `build`, `clean`, `help`.

### 3. Execução no WSL

Se você for rodar o app no **WSL** (Windows Subsystem for Linux), use o script [`wsl-setup.sh`](wsl-setup.sh) em vez do `setup.sh`. Ele executa os mesmos passos (verificação do Docker, criação do `.env`, build e `docker compose up`), mas resolve os caminhos com `ROOT_DIR` absoluto — evitando falhas ao trocar de diretório durante o build no WSL.

```bash
chmod +x wsl-setup.sh
./wsl-setup.sh          # inicia todos os serviços (padrão)
./wsl-setup.sh stop     # para os serviços
./wsl-setup.sh help     # lista todos os comandos
```

### 4. Acesse os serviços

| Serviço | URL | Credenciais (dev) |
|---------|-----|-------------------|
| **Frontend** | http://localhost:8051 | Login: `ADMIN_USER` / `ADMIN_PASSWORD` do `.env` |
| **Upload API** | http://localhost:8001/docs | JWT após login |
| **AI API** | http://localhost:8003/docs | JWT |
| **Report API** | http://localhost:8004/docs | JWT |
| **RabbitMQ** | http://localhost:15672 | `RABBITMQ_USER` / `RABBITMQ_PASSWORD` |
| **PostgreSQL** | localhost:5432 | `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| **MinIO Console** | http://localhost:9001 | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` |
| **MinIO API** | http://localhost:9000 | idem |
| **Prometheus** | http://localhost:9090 | — |
| **Grafana** | http://localhost:3000 | `GRAFANA_USER` / `GRAFANA_PASSWORD` |
| **Loki** | http://localhost:3100 | interno |

---

## Configuração

Principais variáveis em `infrastructure/.env` (ver [`infrastructure/.env.example`](infrastructure/.env.example)):

```env
# Banco e fila
POSTGRES_USER=fiap
POSTGRES_PASSWORD=<senha-forte>
RABBITMQ_USER=fiap
RABBITMQ_PASSWORD=<senha-forte>

# LLM (OpenAI-compatible / OpenRouter)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-v3.2
LLM_OCR=google/gemma-4-26b-a4b-it

# Autenticação (compartilhado entre os três serviços)
JWT_SECRET_KEY=<minimo-48-chars-aleatorios>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
ADMIN_USER=fiap
ADMIN_PASSWORD=<senha-forte>
ALLOWED_ORIGINS=http://localhost:8051

# MinIO
MINIO_ACCESS_KEY=fiap
MINIO_SECRET_KEY=<senha-forte>
MINIO_BUCKET=fiap

# Report Service — chamadas service-to-service ao Upload Service
UPLOAD_SERVICE_URL=http://upload-service:8001
UPLOAD_SERVICE_USER=${ADMIN_USER}
UPLOAD_SERVICE_PASSWORD=${ADMIN_PASSWORD}

# Grafana
GRAFANA_USER=fiap
GRAFANA_PASSWORD=<senha-forte>

# Logs
LOG_LEVEL=INFO
```

---

## Segurança

### Autenticação e autorização

- **JWT**: o Upload Service emite tokens (`POST /upload-service/token` via proxy do frontend); AI e Report Service validam o mesmo `JWT_SECRET_KEY`.
- **Service-to-service**: o Report Service obtém um token via `POST /token` com `UPLOAD_SERVICE_USER`/`PASSWORD` e o renova automaticamente 60 s antes do vencimento.
- **Rate limiting** nos serviços FastAPI (SlowAPI).
- **Headers de segurança** e **CORS** restrito (`ALLOWED_ORIGINS`).

### Validação de entrada

- Upload: limite de **10 MB** e tipos permitidos no Upload Service.
- Processamento: validação de extensão e MIME real (`python-magic`) no AI Service.
- Resposta da IA: JSON com schema Pydantic (`components`, `risks`, `summary`); mascaramento de dados sensíveis antes da análise subsequente.

### Verificação antes do deploy

```bash
./scripts/security-check.sh
```

O script valida `JWT_SECRET_KEY`, CORS, diretório de logs, configurações de banco/MinIO/RabbitMQ e sintaxe Python dos serviços.

---

## Funcionalidades

### Upload

- Formatos: PNG, JPG, JPEG, PDF (e outros validados no AI Service: BMP, GIF, WEBP).
- Armazenamento no MinIO; metadados e status em `arch_uploads`.

### Processamento (AI Service)

- Consumo assíncrono via RabbitMQ (`aio-pika`, prefetch=1).
- OCR multimodal com LLM (Gemma 4 26B via OpenRouter); fallback Tesseract.
- Swarm de agentes Strands (DeepSeek v3.2) para arquitetura, infraestrutura e desenvolvimento; consolidação em JSON.
- Resultado publicado na fila `diagram.result` — **sem escrita direta em banco de dados**.

### Relatórios e dashboard

- Componentes, riscos, recomendações e resumo.
- Listagem por status e download do anexo original.
- Estatísticas combinadas: contagens de uploads (banco `arch_uploads`) + avaliações de feedback (banco `arch_reports`).
- Feedback com avaliação 1–5 estrelas e comentário.

---

## Bancos de dados

O PostgreSQL roda em instância única com dois bancos dedicados, cada um de propriedade exclusiva de um serviço:

| Banco | Dono | Tabelas |
|-------|------|---------|
| `arch_uploads` | Upload Service | `uploads`, `users` |
| `arch_reports` | Report Service | `feedback` |

**Criação automática:**
- **Docker Compose**: o serviço `postgres-setup` executa `createdb` de forma idempotente após o PostgreSQL ficar disponível.
- **Kubernetes**: cada pod (upload-service e report-service) possui um `initContainer create-db` que cria o banco antes do container principal iniciar.
- **Fresh deploy**: o script `infrastructure/postgres/init-databases.sh` cria ambos os bancos na primeira inicialização.

---

## Observabilidade

### Métricas — Prometheus + Grafana

- Endpoints `/metrics` nos serviços FastAPI (`prometheus-fastapi-instrumentator`).
- No Kubernetes: auto-descoberta de pods via annotations `prometheus.io/scrape`.
- Dashboards provisionados: **Arch Analyzer - Overview** e **Arch Analyzer - Logs**.

### Logs — Loki + Promtail

- Logs JSON estruturados (`timestamp`, `level`, `service`, `name`, `message`).
- Docker Compose: Promtail coleta via socket Docker (`/var/run/docker.sock`).
- Kubernetes: Promtail como DaemonSet lendo `/var/log/pods/` — namespace `arch-geral`.

Acesse o Grafana em http://localhost:3000 → Dashboards → **Arch Analyzer - Logs**.

---

## Testes automatizados (pipelines)

Os testes de regressão rodam no **GitHub Actions** com **Python 3.12** e `pytest -q`. Cada microsserviço tem um workflow reutilizável (`reusable-*-tests.yml`) chamado por:

| Workflow | Gatilho | O que executa |
|----------|---------|---------------|
| `upload-service-test.yml` | PR para `main` / manual | `reusable-upload-service-tests.yml` |
| `ai-service-tests.yml` | PR para `main` / manual | `reusable-ai-service-tests.yml` |
| `report-service-tests.yml` | PR para `main` / manual | `reusable-report-service-tests.yml` |
| `deploy.yml` | push em `main` ou `hmg` | Os três testes acima **antes** do build e deploy |

Cada job instala `requirements.txt` + `requirements-dev.txt` do serviço e executa apenas testes **unitários** (sem chamadas reais a APIs pagas de LLM).

### Escopo por serviço

| Serviço | Diretório de testes | Exemplos cobertos |
|---------|---------------------|-------------------|
| **upload-service** | `services/upload-service/tests/` | Caso de uso de upload (`test_upload_file.py`), adaptador PostgreSQL |
| **ai-service** | `services/ai-service/tests/unit/` | Adaptadores LLM, OCR, parser JSON e swarm multiagente (mocks) |
| **report-service** | `services/report-service/tests/` | Adaptador asyncpg de feedback e estatísticas |

O `pytest.ini` do AI Service restringe `testpaths` a `tests/unit`, de modo que a pasta `tests/ragas_eval/` **não** entra no `pytest` da pipeline.

### Executar localmente (mesmo comando da CI)

```bash
# upload-service
cd services/upload-service
pip install -r requirements.txt -r requirements-dev.txt
pytest -q

# ai-service
cd services/ai-service
pip install -r requirements.txt -r requirements-dev.txt
pytest -q

# report-service
cd services/report-service
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

Detalhes dos workflows: [`.github/workflows/README.md`](.github/workflows/README.md).

---

## Avaliação RAGAS (local)

Além dos testes unitários, o **AI Service** inclui uma avaliação comportamental com [Ragas](https://docs.ragas.io) em [`services/ai-service/tests/ragas_eval/`](services/ai-service/tests/ragas_eval/). Ela exercita o fluxo real do `SwarmLlmAdapter` contra amostras de OCR curadas e aplica critérios em linguagem natural (`AspectCritic`):

| Métrica | O que verifica |
|---------|----------------|
| `brazilian_portuguese` | Resposta em português brasileiro |
| `grounded_in_input` | Componentes alinhados ao texto OCR (sem alucinação) |
| `risks_and_mitigations` | Pelo menos 3 riscos com mitigação/recomendação |
| `components_match_topology` | Lista de componentes reflete a topologia do diagrama |

### Por que não roda na nuvem (CI/CD)

Essa avaliação **não** faz parte das pipelines do GitHub Actions. Cada execução dispara chamadas reais ao provedor LLM (swarm + juiz Ragas), o que gera **custo por análise** e tempo de execução elevado — inviável para rodar a cada PR ou deploy.

### Como rodar localmente

```bash
cd services/ai-service
pip install -r requirements-eval.txt

python tests/ragas_eval/evals.py                               # todas as amostras
python tests/ragas_eval/evals.py --sample ecommerce_microservices
python tests/ragas_eval/evals.py --no-save                     # sem gravar CSV
```

Documentação completa: [`services/ai-service/tests/ragas_eval/README.md`](services/ai-service/tests/ragas_eval/README.md).

---

## CI/CD

Workflows em [`.github/workflows/`](.github/workflows/README.md):

| Workflow | Gatilho | Função |
|----------|---------|--------|
| `upload-service-test.yml`, `ai-service-tests.yml`, `report-service-tests.yml` | PR para `main` | `pytest` unitário por serviço |
| `deploy.yml` | push em `main` ou `hmg` | Testes → build/push GHCR → deploy Kubernetes na VPS |
| `setup-vps.yml` | manual | Setup inicial da VPS (Kind, Nginx, SSL) |

**Namespaces Kubernetes:** `arch-prod` (branch main), `arch-hmg` (branch hmg), `arch-geral` (observabilidade compartilhada).

Manifests Kubernetes: [`infrastructure/k8s/`](infrastructure/k8s/README.md). Scripts de setup da VPS: [`.vps/README.md`](.vps/README.md).

---

## Desenvolvimento local

### Sem Docker (apenas APIs)

```bash
cd services/upload-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

O frontend em Docker usa proxy Nginx; sem Compose, as rotas `/upload-service`, `/ai-service` e `/report-service` não estarão disponíveis.

### Frontend estático isolado

```bash
cd frontend
python -m http.server 8051
```

---

## Troubleshooting

### Serviços não sobem

```bash
cd infrastructure
docker compose logs <servico>
docker compose ps
```

### Banco de dados não encontrado (arch_uploads / arch_reports)

O serviço `postgres-setup` cria os bancos automaticamente. Se ele falhar:

```bash
docker compose logs postgres-setup
# Recriar manualmente:
docker compose run --rm postgres-setup
```

### Erro de conexão com banco

```bash
docker compose ps postgres
docker compose logs postgres
```

### RabbitMQ / MinIO

```bash
docker compose logs rabbitmq
docker compose logs minio
```

### Frontend não alcança as APIs

Confirme que o stack Compose está na mesma rede e verifique `docker compose logs frontend`.

---

## MinIO (referência rápida)

```bash
# Listar objetos no bucket
docker exec arch-analyzer-minio mc ls local/fiap/

# Download via curl
curl -O http://localhost:9000/fiap/arquivo.png -u username:password
```

Bucket padrão: `fiap` (configurável via `MINIO_BUCKET`).

---

## Limitações e evoluções

- Qualidade da análise depende da resolução e clareza do diagrama.
- Volumes `emptyDir` no Kubernetes perdem dados no restart do pod; para persistência cross-pod usar PVC com `ReadWriteMany`.
- Endurecer TLS, rotação de segredos e políticas de rede para ambiente real.

---

## Licença

MIT — Hackathon FIAP 2026
