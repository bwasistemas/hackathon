# Workflows GitHub Actions — Arch Analyzer

## Visao geral

| Workflow | Acionado por | O que faz |
|---|---|---|
| `deploy.yml` | push em `main` ou `hmg` / manual | Testa, builda, pusha GHCR e deploya na VPS |
| `setup-vps.yml` | somente manual | Setup inicial completo da VPS |
| `ai-service-tests.yml` | PR para `main` / manual | Roda testes do ai-service |
| `report-service-tests.yml` | PR para `main` / manual | Roda testes do report-service |
| `upload-service-test.yml` | PR para `main` / manual | Roda testes do upload-service |
| `reusable-ai-service-tests.yml` | chamado por outros workflows | Logica de teste reutilizavel |
| `reusable-report-service-tests.yml` | chamado por outros workflows | Logica de teste reutilizavel |
| `reusable-upload-service-tests.yml` | chamado por outros workflows | Logica de teste reutilizavel |

---

## `deploy.yml` — Pipeline principal de CD

**Acionado por:** `push` nas branches `main` e `hmg`, ou `workflow_dispatch`.

### Jobs

```
test-report-service ─┐
test-ai-service     ─┼─→ build-push ──→ deploy
test-upload-service ─┘
```

#### `test-*` (paralelos)
Rodam os testes dos tres servicos em paralelo antes do build.
Usam os workflows reutilizaveis (`reusable-*`).

#### `build-push`
1. Checkout do repositorio
2. Login no GHCR com `GITHUB_TOKEN`
3. Computa a tag da imagem: `<branch>-<sha curto>` (ex: `main-a1b2c3d`)
4. Build e push de todas as imagens para `ghcr.io/bwasistemas/hackathon/<servico>:<tag>`
   - `frontend`, `upload-service`, `ai-service`, `report-service`, `rabbitmq`
   - Cada servico tambem recebe a tag `<branch>` como alias (ex: `main`, `hmg`)

#### `deploy`
1. **Set deployment vars** — define por branch:
   - `namespace`: `arch-prod` (main) ou `arch-hmg` (hmg)
   - `domain`: dominio de producao ou homologacao
   - NodePorts por ambiente: frontend (30080/81), rabbitmq-mgmt (30086/87)
   - NodePorts fixos (compartilhados via arch-geral): grafana (30082), prometheus (30084)
2. **Checkout** — obtem os manifests no runner
3. **SCP x3** (`appleboy/scp-action`):
   - `infrastructure/k8s/` → `/tmp/arch-k8s-<namespace>/` (manifests da aplicacao)
   - `infrastructure/k8s-geral/` → `/tmp/arch-k8s-geral/` (observabilidade compartilhada)
   - `.vps/nginx-archanalyzer.conf` → `/tmp/arch-nginx-update/` (config Nginx)
4. **SSH** (`appleboy/ssh-action`) — na VPS:
   - Valida secrets obrigatorios
   - Exporta kubeconfig do cluster Kind (se necessario)
   - Atualiza config Nginx se o template mudou
   - Configura socat: frontend e rabbitmq-mgmt (por ambiente) + grafana:30082 e prometheus:30084 (fixos)
   - Instala KEDA se os CRDs nao existirem
   - Cria/atualiza namespace, pull secret GHCR, `arch-secrets`, `rabbitmq-keda-auth`
   - Aplica manifests de `k8s/`: `envsubst | kubectl apply` em ordem numerica
   - Aplica manifests de `k8s-geral/` (namespace arch-geral): cria `grafana-secrets`, apply Prometheus/Grafana/Loki/Promtail
   - Aguarda rollout dos servicos criticos (app) e da observabilidade (arch-geral, nao critico)
   - Smoke test HTTP no frontend
   - Exibe status dos pods e logs de containers com erro

---

## `setup-vps.yml` — Setup inicial da VPS

**Acionado por:** somente `workflow_dispatch` (manual via GitHub UI ou CLI).

Conecta na VPS via SSH e executa:
1. `setup-vps.sh` — se o Kind nao estiver instalado:
   - Docker, Kind, kubectl, Helm, KEDA, Nginx, SSL prod, Portainer, Headlamp
2. `setup-deploy.sh` — sempre:
   - Clona repositorio em `/opt/arch-analyzer/prod` e `/hmg`
   - Cria arquivos `.env` para docker-compose local
   - Configura Nginx
   - Gera SSL para o dominio de homologacao

**Inputs disponiveis:**

| Input | Padrao | Quando usar |
|---|---|---|
| `skip_ssl_hmg` | false | DNS de `archanalyzerhmg.*` ainda nao propagou |
| `skip_dns_check` | false | DNS configurado mas sem verificacao |
| `force_env` | true | Recriar `.env` mesmo se ja existir |

> Idempotente: verifica o que ja esta instalado antes de instalar.
> Pode ser acionado novamente sem risco de duplicacao.

---

## `reusable-*.yml` — Workflows reutilizaveis de teste

Tres arquivos com a logica real dos testes, acionados via `workflow_call`:

| Arquivo | Servico testado | Diretorio |
|---|---|---|
| `reusable-ai-service-tests.yml` | ai-service | `services/ai-service` |
| `reusable-report-service-tests.yml` | report-service | `services/report-service` |
| `reusable-upload-service-tests.yml` | upload-service | `services/upload-service` |

Cada um faz: checkout → setup Python → `pip install` → `pytest`.
Sao chamados por tres fontes:
- `deploy.yml` (jobs `test-*`) — testes obrigatorios antes do deploy
- `*-tests.yml` (gatilhos de PR) — testes em pull requests
- `workflow_dispatch` — execucao manual isolada

---

## `*-tests.yml` — Gatilhos de PR

Tres arquivos finos que so definem o gatilho, sem logica propria:

| Arquivo | Delega para |
|---|---|
| `ai-service-tests.yml` | `reusable-ai-service-tests.yml` |
| `report-service-tests.yml` | `reusable-report-service-tests.yml` |
| `upload-service-test.yml` | `reusable-upload-service-tests.yml` |

Acionados em: `pull_request` para `main` e `workflow_dispatch`.
A separacao entre gatilho e logica permite que o `deploy.yml` reutilize
os mesmos testes sem duplicar codigo.
