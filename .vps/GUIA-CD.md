# Guia de CD — Arch Analyzer

## Arquitetura de Deploy

```
GitHub Actions (CI/CD)
│
├─ push main ──→ testes ──→ build imagens ──→ push GHCR ──→ SSH ──→ VPS prod
└─ push hmg  ──→ testes ──→ build imagens ──→ push GHCR ──→ SSH ──→ VPS hmg
                                                                        │
VPS                                                                      │
├─ Nginx (80/443) ← SSL Let's Encrypt                                   │
│   ├─ archanalyzer.brunoretiro.com.br/           → Kind NodePort 30080 (arch-prod)
│   ├─ hmg.archanalyzer.brunoretiro.com.br/       → Kind NodePort 30081 (arch-hmg)
│   ├─ archanalyzer.brunoretiro.com.br/portainer/ → Portainer :9000
│   └─ archanalyzer.brunoretiro.com.br/k8s/       → Headlamp  :30444
│
├─ Kind cluster (2 workers)
│   ├─ Namespace arch-prod (produção — branch main)
│   │   frontend:30080, upload:8001, ai:8003, report:8004
│   │   postgres:5432, rabbitmq:5672, minio:9000, prometheus:9090, grafana:3000
│   │
│   └─ Namespace arch-hmg (homologação — branch hmg)
│       frontend:30081 (host), mesmos serviços internos
│
├─ KEDA v2.14 — autoscaling do ai-service
│   ScaledObject: min=1, max=MAX_REPLICAS, trigger=queue diagram.upload
│
└─ Portainer + Headlamp — UIs de gerenciamento
```

---

## O deploy usa Kubernetes (Kind)?

**Sim.** O deploy usa **kubectl aplicando manifests no cluster Kind** da própria VPS.

O Nginx aponta para NodePorts do Kind:
- Produção: `localhost:30080` (NodePort do frontend no namespace `arch-prod`)
- Homologação: `localhost:30081` (NodePort do frontend no namespace `arch-hmg`)

Os namespaces `arch-prod` e `arch-hmg` separam completamente os ambientes dentro do mesmo cluster.

---

## Autoscaling com KEDA

O `ai-service` escala automaticamente com base na profundidade da fila `diagram.upload` no RabbitMQ.

| Variável GitHub | Padrão | Descrição |
|---|---|---|
| `MAX_REPLICAS` | `5` | Máximo de réplicas do ai-service |
| `QUEUE_MESSAGES_PER_REPLICA` | `5` | Mensagens na fila para subir 1 réplica |

**Como funciona:**
- Fila vazia → 1 réplica (mínimo)
- 5 mensagens → 1 réplica, 10 mensagens → 2 réplicas, ..., ≥ 25 mensagens → 5 réplicas
- Cooldown de 60 segundos antes de escalar para baixo

O KEDA lê a fila via AMQP com a secret `rabbitmq-keda-auth` (injetada a cada deploy).

---

## As mudanças quebram o desenvolvimento local?

**Não.** Para desenvolvimento local, continue usando Docker Compose:

```bash
cd infrastructure
docker compose up
```

O `docker-compose.yml` usa variáveis com valores padrão (`${PORT:-default}`) e continua funcionando sem qualquer mudança.

Os manifests Kubernetes em `infrastructure/k8s/` são usados **apenas** pelo pipeline de deploy.

---

## Estrutura dos Scripts `.vps/`

| Script | Responsabilidade |
|---|---|
| `setup-vps.sh` | Orchestrador — instala Docker, Kind, kubectl, KEDA, Nginx, SSL, Portainer, Headlamp |
| `setup-deploy.sh` | Orchestrador de CD — clona repo, cria .env, configura Nginx, gera SSL HMG |
| `setup-dirs.sh` | Clona/atualiza repositório nos diretórios de deploy |
| `setup-env.sh` | Cria arquivos `.env` para prod e hmg (prompts mínimos) |
| `setup-nginx.sh` | Configura Nginx e recarrega |
| `setup-ssl-hmg.sh` | Gera certificado SSL para `hmg.archanalyzer.brunoretiro.com.br` |
| `lib.sh` | Funções compartilhadas (logging, cores, utilitários) |
| `nginx-archanalyzer.conf` | Template Nginx (setup-nginx.sh substitui os placeholders) |

**Uso rápido (tudo de uma vez):**
```bash
sudo ./setup-vps.sh seu@email.com
```

---

## Secrets e Variables necessários no GitHub

Acesse: `github.com/bwasistemas/hackathon → Settings → Secrets and variables → Actions`

### Secrets (valores sensíveis)

| Secret | Descrição |
|---|---|
| `VPS_HOST` | IP público da VPS |
| `VPS_USER` | usuário SSH (`root` ou `ubuntu`) |
| `VPS_SSH_KEY` | conteúdo da chave privada SSH (sem passphrase) |
| `VPS_SSH_PORT` | porta SSH — omita se for a 22 |
| `LETSENCRYPT_EMAIL` | email para certificados Let's Encrypt |
| `POSTGRES_USER` | usuário do PostgreSQL |
| `POSTGRES_PASSWORD` | senha do PostgreSQL |
| `RABBITMQ_USER` | usuário do RabbitMQ |
| `RABBITMQ_PASSWORD` | senha do RabbitMQ |
| `OPENAI_API_KEY` | chave da API OpenAI / OpenRouter |
| `JWT_SECRET_KEY` | chave de assinatura dos JWTs (≥ 48 chars aleatórios) |
| `ADMIN_USER` | usuário admin da aplicação |
| `ADMIN_PASSWORD` | senha do usuário admin da aplicação |
| `MINIO_ACCESS_KEY` | usuário root do MinIO (MINIO_ROOT_USER) |
| `MINIO_SECRET_KEY` | senha root do MinIO (MINIO_ROOT_PASSWORD) |
| `GRAFANA_USER` | usuário do Grafana |
| `GRAFANA_PASSWORD` | senha do Grafana |

> O `GITHUB_TOKEN` **não precisa ser configurado** — é gerado automaticamente pelo GitHub Actions.
>
> O pipeline cria/atualiza os Kubernetes Secrets a cada deploy com esses valores,
> então **não é preciso rodar `setup-env.sh` manualmente** antes do primeiro deploy.

### Variables (valores não sensíveis)

Na mesma tela, aba **Variables** (não Secrets):

| Variable | Padrão | Descrição |
|---|---|---|
| `DOMAIN_PROD` | `archanalyzer.brunoretiro.com.br` | Domínio de produção |
| `DOMAIN_HMG` | `hmg.archanalyzer.brunoretiro.com.br` | Domínio de homologação |
| `MAX_REPLICAS` | `5` | Máximo de réplicas do ai-service (KEDA) |
| `QUEUE_MESSAGES_PER_REPLICA` | `5` | Mensagens por réplica para escala do ai-service |
| `POSTGRES_DB` | `fiap` | Nome do banco de dados |
| `MINIO_BUCKET` | `fiap` | Nome do bucket MinIO |
| `TZ` | `America/Sao_Paulo` | Fuso horário dos containers |

**Gerar chave SSH dedicada para o CI:**
```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key -N ""
# Copiar chave pública para a VPS:
ssh-copy-id -i ~/.ssh/deploy_key.pub USUARIO@IP_DA_VPS
# Conteúdo de ~/.ssh/deploy_key vai no secret VPS_SSH_KEY
```

---

## Fluxo de primeiro setup (passo a passo)

```
1. DNS     : criar registro A  archanalyzer.brunoretiro.com.br → IP da VPS
             criar registro A  hmg.archanalyzer.brunoretiro.com.br → IP da VPS
2. GitHub  : criar os secrets e variables acima
3. VPS     : executar ./setup-vps.sh (instala Kind, KEDA, Nginx, SSL, Portainer, Headlamp)
             OU acionar o workflow "Setup VPS (first-time)" manualmente
4. GitHub  : push na branch main → deploy automático de produção (namespace arch-prod)
5. GitHub  : push na branch hmg  → deploy automático de homologação (namespace arch-hmg)
```

### Opções do workflow "Setup VPS (first-time)"

| Input | Padrão | Quando usar |
|---|---|---|
| Pular SSL HMG | false | DNS ainda não propagou |
| Pular verificação DNS | false | Tem certeza que o DNS está certo |
| Recriar .env | false | Precisa reconfigurar credenciais |

---

## Solução de problemas comuns

**Deploy falha com "namespace not found"**
```bash
# Execute o setup na VPS:
sudo bash /opt/arch-analyzer/prod/.vps/setup-vps.sh
```

**Nginx retorna 502**
```bash
# Verificar se os pods estão rodando:
kubectl get pods -n arch-prod
# Verificar logs do frontend:
kubectl logs -n arch-prod deployment/frontend
```

**GHCR: permission denied ao fazer pull**
```bash
# O token expira com o workflow. Para pull manual, use um PAT:
echo "ghp_SEU_PAT" | docker login ghcr.io -u SEU_USUARIO --password-stdin
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io --docker-username=SEU_USUARIO \
  --docker-password=ghp_SEU_PAT -n arch-prod --dry-run=client -o yaml | kubectl apply -f -
```

**KEDA não está escalando**
```bash
# Verificar estado do ScaledObject:
kubectl describe scaledobject ai-service-scaler -n arch-prod
# Verificar se a fila existe no RabbitMQ:
kubectl exec -n arch-prod statefulset/rabbitmq -- rabbitmqctl list_queues
```

**Ver logs do ai-service**
```bash
kubectl logs -n arch-prod deployment/ai-service --follow
# Verificar autoscaling:
kubectl get hpa -n arch-prod
```
