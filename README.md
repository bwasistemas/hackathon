# Arch Analyzer

MVP para análise automatizada de diagramas de arquitetura de software (imagens ou PDF), com microsserviços, mensageria, persistência, observabilidade e pipeline de IA integrado ao fluxo real de upload.

**Repositório:** [github.com/bwasistemas/hackathon](https://github.com/bwasistemas/hackathon)

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
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│  Upload Service  │────▶│    RabbitMQ     │
│  (Nginx/SPA)    │     │   (FastAPI)      │     │   (Message Q)   │
│   :8051         │     │   :8001          │     │   :5672/:15672  │
└─────────────────┘     └───────┬──────────┘     └────────┬────────┘
                                │                         │
                                │ store file              │ notify
                                ▼                         ▼
                        ┌─────────────────┐     ┌──────────────────┐
                        │     MinIO       │◀────│   AI Service     │
                        │  (Object Store) │     │   (LLM + OCR)    │
                        │  :9000/:9001    │     │   :8003          │
                        └─────────────────┘     └───────┬──────────┘
                                                        │
                                                        │ persist result
                                                        ▼
┌──────────────────┐                          ┌──────────────────┐
│  Report Service  │◀─────────────────────────│   PostgreSQL     │
│   (FastAPI)      │                          │   :5432          │
│   :8004          │                          └──────────────────┘
└──────────────────┘

Observabilidade (logs + métricas):

┌──────────────┐   scrape   ┌──────────────┐   datasource  ┌──────────────┐
│  Prometheus  │──────────▶│    Grafana    │◀─────────────│     Loki     │
│   :9090      │            │    :3000      │               │    :3100     │
└──────────────┘            └──────────────┘               └──────╲───────┘
                                                                   ║ push logs
                                                            ┌──────╚───────┐
                                                            │   Promtail   │
                                                            │ (Docker logs)│
                                                            └──────────────┘
```

| Componente | Responsabilidade |
|------------|------------------|
| **Frontend** | SPA estática (Nginx): upload, acompanhamento de status, relatórios e feedback. Login JWT via proxy na mesma origem. |
| **Upload Service** | Recebe arquivo, valida tamanho/tipo, grava no MinIO, persiste metadados e publica evento no RabbitMQ. |
| **RabbitMQ** | Desacopla upload do processamento de IA. |
| **AI Service** | Consome a fila, valida MIME/extensão/tamanho, extrai conteúdo visual (LLM OCR), executa swarm de agentes LLM e persiste a análise. |
| **Report Service** | Consulta relatórios, anexo original, estatísticas e feedback — sem reprocessar imagens. |
| **PostgreSQL** | Uploads, status, payload de análise e avaliações. |
| **MinIO** | Object storage (S3-compatible) dos arquivos enviados. |
| **Prometheus / Grafana / Loki / Promtail** | Métricas HTTP, dashboards e logs estruturados dos containers. |

Cada serviço FastAPI segue **arquitetura hexagonal** (domínio, aplicação, portas e adaptadores). Detalhes do AI Service: [`doc/ai-service.md`](doc/ai-service.md).

---

## Fluxo principal

1. O usuário envia PNG, JPG, JPEG ou PDF pelo frontend.
2. O **Upload Service** aplica limite de **10 MB**, salva no MinIO e cria registro no PostgreSQL com status `RECEIVED`.
3. O Upload Service publica evento no RabbitMQ (`upload_id`, `filename`, `file_path`, `content_type`).
4. O **AI Service** consome a mensagem, marca `PROCESSING` e baixa o arquivo do MinIO.
5. O AI Service valida extensão, tamanho (até **50 MB** no processamento) e MIME; executa extração visual/OCR e análise com LLM.
6. O resultado é normalizado em JSON (`components`, `risks`, `summary`) e gravado no PostgreSQL com status `DONE`.
7. O **Report Service** e o frontend exibem o relatório, anexo e feedback.

Estados persistidos no código: `RECEIVED`, `PROCESSING`, `DONE`. Falhas de validação e integração são tratadas por exceções HTTP ou payload de erro na análise.

---

## Estrutura do projeto

```
hackathon/
├── frontend/                 # SPA + Nginx (proxy para APIs)
├── services/
│   ├── upload-service/       # Upload, MinIO, fila, emissão JWT
│   ├── ai-service/           # RabbitMQ consumer, OCR/LLM, persistência
│   └── report-service/       # Leitura de relatórios e feedback
├── infrastructure/
│   ├── docker-compose.yml    # Stack local completo
│   ├── docker-compose.prod.yml
│   ├── k8s/                  # Manifests Kubernetes (deploy na VPS)
│   ├── prometheus/ grafana/ loki/ promtail/ rabbitmq/
│   └── .env.example
├── .github/workflows/          # Testes e deploy (GitHub Actions)
├── .vps/                       # Scripts de setup inicial da VPS
├── doc/                        # Documentação técnica em português
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
# Ou python3
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
- **Rate limiting** nos serviços FastAPI (SlowAPI).
- **Headers de segurança** e **CORS** restrito (`ALLOWED_ORIGINS`).

### Validação de entrada

- Upload: limite de **10 MB** e tipos permitidos no Upload Service.
- Processamento: validação de extensão, **50 MB**, MIME real (`python-magic`) no AI Service.
- Resposta da IA: JSON com schema Pydantic (`components`, `risks`, `summary`); mascaramento de dados sensíveis antes da análise subsequente.

### Verificação antes do deploy

```bash
./scripts/security-check.sh
```

O script valida `JWT_SECRET_KEY`, CORS, diretório de logs, configurações de banco/MinIO/RabbitMQ e sintaxe Python dos serviços.

## Funcionalidades

### Upload

- Formatos: PNG, JPG, JPEG, PDF (e outros validados no AI Service: BMP, GIF, WEBP).
- Armazenamento no MinIO; metadados e status no PostgreSQL.

### Processamento (AI Service)

- Consumo assíncrono via RabbitMQ (`aio-pika`).
- Extração visual com `LlmOCRAdapter`; fallback Tesseract quando configurado.
- Swarm de agentes (Strands) para arquitetura, infraestrutura e desenvolvimento; consolidação em JSON.

### Relatórios e dashboard

- Componentes, riscos, recomendações e resumo.
- Listagem por status, anexo original, estatísticas.
- Feedback com avaliação 1–5 estrelas.

---

## Observabilidade

### Métricas — Prometheus + Grafana

- Endpoints `/metrics` nos serviços FastAPI (`prometheus-fastapi-instrumentator`).
- Dashboards provisionados: **Arch Analyzer - Overview** e **Arch Analyzer - Logs**.

### Logs — Loki + Promtail

- Logs JSON estruturados (`timestamp`, `level`, `service`, `name`, `message`).
- Promtail coleta via socket Docker (`/var/run/docker.sock`).

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
| **report-service** | `services/report-service/tests/` | Adaptador asyncpg de relatórios e estatísticas |

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

Além dos testes unitários, o **AI Service** inclui uma avaliação comportamental com [Ragas](https://docs.ragas.io) em [`services/ai-service/tests/ragas_eval/`](services/ai-service/tests/ragas_eval/). Ela exercita o fluxo real do `SwarmLlmAdapter` contra amostras de OCR curadas e aplica critérios em linguagem natural (`AspectCritic`), por exemplo:

| Métrica | O que verifica |
|---------|----------------|
| `brazilian_portuguese` | Resposta em português brasileiro |
| `grounded_in_input` | Componentes alinhados ao texto OCR (sem alucinação) |
| `risks_and_mitigations` | Pelo menos 3 riscos com mitigação/recomendação |
| `components_match_topology` | Lista de componentes reflete a topologia do diagrama |

### Por que não roda na nuvem (CI/CD)

Essa avaliação **não** faz parte das pipelines do GitHub Actions. Cada execução dispara chamadas reais ao provedor LLM (swarm + juiz Ragas), o que gera **custo por análise** e tempo de execução elevado — inviável para rodar a cada PR ou deploy. Por isso ela permanece como script manual para uso local ou em avaliações pontuais da equipe.

### Como rodar localmente

Dependências separadas em `requirements-eval.txt` (não instaladas na CI):

```bash
cd services/ai-service
pip install -r requirements-eval.txt
```

O script carrega automaticamente o `.env` na raiz do repositório (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `LLM_OCR`, etc.).

```bash
# a partir de services/ai-service — todas as amostras
python tests/ragas_eval/evals.py

# uma amostra específica
python tests/ragas_eval/evals.py --sample ecommerce_microservices

# sem gravar CSV
python tests/ragas_eval/evals.py --no-save
```

Saída: tabela de scores no terminal, média por métrica e relatório CSV em `tests/ragas_eval/results/eval_<timestamp>.csv` (salvo com `--no-save`).

Documentação completa da suíte: [`services/ai-service/tests/ragas_eval/README.md`](services/ai-service/tests/ragas_eval/README.md).

---

## CI/CD

Workflows em [`.github/workflows/`](.github/workflows/README.md):

| Workflow | Gatilho | Função |
|----------|---------|--------|
| `upload-service-test.yml`, `ai-service-tests.yml`, `report-service-tests.yml` | PR para `main` | `pytest` unitário por serviço |
| `deploy.yml` | push em `main` ou `hmg` | Testes → build/push GHCR → deploy Kubernetes na VPS |
| `setup-vps.yml` | manual | Setup inicial da VPS (Kind, Nginx, SSL) |

Manifests Kubernetes: [`infrastructure/k8s/`](infrastructure/k8s/README.md). Scripts de primeira instalação da VPS: [`.vps/README.md`](.vps/README.md).

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
- Estados `RECEIVED` / `PROCESSING` / `DONE` cobrem o fluxo feliz; padronizar `ERROR` no banco é evolução recomendada.
- Endurecer TLS, rotação de segredos e políticas de rede para ambiente real.

---

## Licença

MIT — Hackathon FIAP 2026