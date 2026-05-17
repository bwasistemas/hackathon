# Guia de CD — Arch Analyzer

## Arquitetura de Deploy

```
GitHub Actions (CI/CD)
│
├─ push main ──→ testes ──→ build imagens ──→ push GHCR ──→ SCP + SSH ──→ VPS prod
└─ push hmg  ──→ testes ──→ build imagens ──→ push GHCR ──→ SCP + SSH ──→ VPS hmg
                                                                   │
VPS                                                                 │
├─ Nginx (80/443) ← SSL Let's Encrypt                              │
│   ├─ archanalyzer.brunoretiro.com.br/             → Kind NodePort 30080 (frontend prod)
│   ├─ archanalyzer.brunoretiro.com.br/grafana/     → Kind NodePort 30082 (grafana prod)
│   ├─ archanalyzer.brunoretiro.com.br/prometheus/  → Kind NodePort 30084 (prometheus prod)
│   ├─ archanalyzer.brunoretiro.com.br/rabbitmq/    → Kind NodePort 30086 (rabbitmq-mgmt prod)
│   ├─ archanalyzer.brunoretiro.com.br/portainer/  → Portainer Docker :9000
│   ├─ archanalyzer.brunoretiro.com.br/k8s/        → Headlamp :30444
│   │
│   ├─ archanalyzerhmg.brunoretiro.com.br/          → Kind NodePort 30081 (frontend hmg)
│   ├─ archanalyzerhmg.brunoretiro.com.br/grafana/  → Kind NodePort 30082 (grafana compartilhado)
│   ├─ archanalyzerhmg.brunoretiro.com.br/prometheus/→ Kind NodePort 30084 (prometheus compartilhado)
│   └─ archanalyzerhmg.brunoretiro.com.br/rabbitmq/ → Kind NodePort 30087 (rabbitmq-mgmt hmg)
│
├─ Kind cluster (Kubernetes in Docker)
│   ├─ Namespace arch-prod (producao — branch main)
│   │   frontend:30080 · rabbitmq-mgmt:30086
│   │   upload:8001 · ai:8003 · report:8004
│   │   postgres:5432 · rabbitmq:5672 · minio:9000
│   │
│   ├─ Namespace arch-hmg (homologacao — branch hmg)
│   │   frontend:30081 · rabbitmq-mgmt:30087
│   │   mesmos servicos internos, totalmente isolados do prod
│   │
│   └─ Namespace arch-geral (observabilidade compartilhada)
│       grafana:30082 · prometheus:30084 · loki:3100 (interno)
│       Promtail coleta logs de arch-prod e arch-hmg
│
├─ KEDA v2.14 — autoscaling do ai-service
│   ScaledObject: min=1, max=MAX_REPLICAS, trigger=fila diagram.upload
│
└─ Portainer + Headlamp — UIs de gerenciamento (compartilhadas entre prod e hmg)
```

---

## Como o deploy funciona (a cada push)

O pipeline **nao clona o repositorio na VPS**. O runner do GitHub Actions ja tem o
codigo via `actions/checkout` e o transfere para a VPS apenas os manifests necessarios:

```
Runner (GitHub Actions)
  1. checkout            → obtem infrastructure/k8s/
  2. scp-action          → copia k8s/ para /tmp/arch-k8s-<namespace>/ na VPS
  3. ssh-action          → na VPS:
       - cria secrets Kubernetes (arch-secrets, ghcr-pull-secret, etc.)
       - envsubst nas variaveis dos manifests
       - kubectl apply -n <namespace>
       - aguarda rollouts + smoke test
       - rm -rf /tmp/arch-k8s-<namespace>/
```

---

## Autoscaling com KEDA

O `ai-service` escala automaticamente com base na profundidade da fila `diagram.upload` no RabbitMQ.

| Variavel GitHub | Padrao | Descricao |
|---|---|---|
| `MAX_REPLICAS` | `5` | Maximo de replicas do ai-service |
| `QUEUE_MESSAGES_PER_REPLICA` | `5` | Mensagens na fila para subir 1 replica |

- Fila vazia → 1 replica (minimo)
- 5 mensagens → 1 replica, 10 → 2, ... >= 25 → 5 replicas
- Cooldown de 60 segundos antes de escalar para baixo

---

## Desenvolvimento local

Para desenvolvimento local, continue usando Docker Compose — nenhuma alteracao necessaria:

```bash
cd infrastructure
docker compose up
```

Os manifests em `infrastructure/k8s/` sao usados **apenas** pelo pipeline de deploy.
O `.env` em `infrastructure/` serve apenas para o Docker Compose local.

---

## Estrutura dos Scripts `.vps/`

| Arquivo | Responsabilidade | Quando e chamado |
|---|---|---|
| `setup-vps.sh` | Instala Docker, Kind, kubectl, KEDA, Nginx, SSL prod, Portainer, Headlamp | `setup-vps.yml` (se Kind ausente) |
| `setup-deploy.sh` | Orquestrador: chama os 4 scripts abaixo em sequencia | `setup-vps.yml` (sempre) |
| `setup-dirs.sh` | Clona/atualiza repositorio em `/opt/arch-analyzer/prod` e `/hmg` | `setup-deploy.sh` |
| `setup-env.sh` | Cria `.env` para docker-compose local (nao afeta o deploy K8s) | `setup-deploy.sh` |
| `setup-nginx.sh` | Aplica `nginx-archanalyzer.conf` com os dominios reais e recarrega Nginx | `setup-deploy.sh` |
| `setup-ssl-hmg.sh` | Gera cert SSL para `archanalyzerhmg.*` via certbot | `setup-deploy.sh` |
| `lib.sh` | Funcoes compartilhadas (logging colorido, `require_root`) | `source` pelos outros scripts |
| `nginx-archanalyzer.conf` | Template Nginx com placeholders `__DOMAIN_PROD__` e `__DOMAIN_HMG__` | Processado pelo `setup-nginx.sh` |
| `fix-vps.sh` | Recria socat para porta 30444 (Headlamp) em clusters sem mapeamento | Execucao manual |
| `uninstall-vps.sh` | Remove tudo que o setup-vps.sh instalou | Execucao manual |

---

## Configuracao de Secrets e Variables no GitHub

Acesse: `github.com/bwasistemas/hackathon → Settings → Secrets and variables → Actions`

---

### 1. VPS_SSH_KEY — Chave SSH para o CI acessar a VPS

O pipeline conecta na VPS via SSH para fazer o deploy. E necessario uma chave dedicada.

**Como gerar e configurar:**

```bash
# 1. Gerar par de chaves (sem passphrase — obrigatorio para CI nao-interativo)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key -N ""

# 2. Adicionar a chave PUBLICA na VPS (substitua USUARIO e IP)
ssh-copy-id -i ~/.ssh/deploy_key.pub USUARIO@IP_DA_VPS

# Ou manualmente na VPS:
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# 3. Verificar que a conexao funciona antes de configurar o secret
ssh -i ~/.ssh/deploy_key USUARIO@IP_DA_VPS "echo conexao ok"
```

**Adicionar no GitHub:**

- `VPS_SSH_KEY`: conteudo completo de `~/.ssh/deploy_key` (chave PRIVADA)
  - Incluir as linhas `-----BEGIN OPENSSH PRIVATE KEY-----` e `-----END OPENSSH PRIVATE KEY-----`
  - Colar exatamente como saiu do `cat ~/.ssh/deploy_key` — sem espacos extras

**Sintomas de configuracao errada:**

| Erro | Causa | Solucao |
|---|---|---|
| `ssh: no key found` | Secret vazio ou formato invalido | Recriar o secret com o conteudo completo da chave |
| `attempted methods [none], no supported methods remain` | Mesma causa acima | Idem |
| `attempted methods [none publickey], no supported methods remain` | Chave publica nao esta no `authorized_keys` da VPS | Rodar `ssh-copy-id` conforme acima |

---

### 2. GH_DEPLOY_KEY — Chave SSH para clonar o repositorio na VPS

Usado pelo workflow `setup-vps.yml` para clonar o repositorio em `/opt/arch-analyzer/`.
O pipeline de deploy dia-a-dia (`deploy.yml`) **nao usa esta chave** — ele transfere
os manifests via SCP diretamente do runner.

**Como configurar (uma vez na VPS):**

```bash
# 1. Gerar chave dedicada para o GitHub (na VPS, como o usuario de deploy)
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""

# 2. Exibir a chave publica — copiar o conteudo
cat ~/.ssh/github_deploy.pub
```

**Adicionar a chave publica como Deploy Key no GitHub:**

`github.com/bwasistemas/hackathon → Settings → Deploy keys → Add deploy key`
- Title: `VPS Deploy Key`
- Key: colar o conteudo de `~/.ssh/github_deploy.pub`
- Allow write access: **nao** (leitura e suficiente para clone)

**Adicionar a chave privada como Secret no GitHub:**

- `GH_DEPLOY_KEY`: conteudo de `~/.ssh/github_deploy` (chave privada)

---

### 3. GHCR_PAT — Token de longa duracao para pull de imagens

O `GITHUB_TOKEN` do Actions expira ao fim do workflow. Se o KEDA precisar escalar
o `ai-service` horas depois do deploy, o pull da imagem falharia com 403.

**Como criar:**

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Criar token com escopo `read:packages` no repositorio `bwasistemas/hackathon`
3. Adicionar como secret `GHCR_PAT`

O pipeline usa `GHCR_PAT` se disponivel, com fallback para `GITHUB_TOKEN`.

---

### 4. OPENAI_API_KEY, ADMIN_USER, ADMIN_PASSWORD — obrigatorios desde esta versao

A partir desta versao o deploy valida todos os secrets criticos antes de aplicar.
Os seguintes secrets, anteriormente opcionais, agora sao obrigatorios:

| Secret | Descricao |
|---|---|
| `OPENAI_API_KEY` | Chave de API para o ai-service chamar o LLM |
| `ADMIN_USER` | Usuario administrador da aplicacao |
| `ADMIN_PASSWORD` | Senha do usuario administrador |

Se ja estiverem configurados, nenhuma acao e necessaria.

---

### 5. Tabela completa de Secrets

| Secret | Descricao |
|---|---|
| `VPS_HOST` | IP publico ou hostname da VPS |
| `VPS_USER` | Usuario SSH da VPS (`ubuntu`, `root`, etc.) |
| `VPS_SSH_KEY` | Conteudo da chave privada SSH para acesso do CI a VPS |
| `VPS_SSH_PORT` | Porta SSH — omitir se for a padrao 22 |
| `GH_DEPLOY_KEY` | Chave privada SSH para o `setup-vps.yml` clonar o repo na VPS |
| `LETSENCRYPT_EMAIL` | Email para notificacoes e renovacao dos certs SSL |
| `GHCR_PAT` | PAT com `read:packages` — evita 403 no KEDA pos-deploy |
| `POSTGRES_USER` | Usuario do PostgreSQL |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL |
| `RABBITMQ_USER` | Usuario do RabbitMQ |
| `RABBITMQ_PASSWORD` | Senha do RabbitMQ |
| `OPENAI_API_KEY` | Chave da API OpenAI / OpenRouter |
| `JWT_SECRET_KEY` | Chave de assinatura dos JWTs (minimo 48 chars aleatorios) |
| `ADMIN_USER` | Usuario admin da aplicacao |
| `ADMIN_PASSWORD` | Senha do usuario admin da aplicacao |
| `MINIO_ACCESS_KEY` | Usuario root do MinIO — minimo 3 caracteres |
| `MINIO_SECRET_KEY` | Senha root do MinIO — minimo 8 caracteres |
| `GRAFANA_USER` | Usuario do Grafana |
| `GRAFANA_PASSWORD` | Senha do Grafana |

O pipeline cria/atualiza os Kubernetes Secrets a cada deploy automaticamente.

---

### 5. Tabela de Variables (valores nao sensiveis)

Aba **Variables** (nao Secrets) na mesma tela:

| Variable | Valor | Descricao |
|---|---|---|
| `REPO_SSH_URL` | `git@github.com:bwasistemas/hackathon.git` | URL SSH do repositorio (usado pelo `setup-vps.yml` para clone) |
| `DOMAIN_PROD` | `archanalyzer.brunoretiro.com.br` | Dominio de producao |
| `DOMAIN_HMG` | `archanalyzerhmg.brunoretiro.com.br` | Dominio de homologacao |
| `MAX_REPLICAS` | `5` | Maximo de replicas do ai-service (KEDA) |
| `QUEUE_MESSAGES_PER_REPLICA` | `5` | Mensagens por replica para escala |
| `POSTGRES_DB` | `fiap` | Nome do banco de dados |
| `MINIO_BUCKET` | `fiap` | Nome do bucket MinIO |
| `TZ` | `America/Sao_Paulo` | Fuso horario dos containers |

---

## Acoes manuais necessarias apos esta atualizacao

### Re-executar "Setup VPS - first-time" uma vez

O `deploy.yml` agora atualiza o Nginx automaticamente a cada push (sem precisar
acionar o setup manualmente). Para isso, o `setup-vps.sh` precisa ter criado:

- `/usr/local/bin/arch-nginx-apply` — script wrapper de reload do Nginx
- `/etc/sudoers.d/arch-deploy-nginx` — permissao para o deploy user recarregar o Nginx sem senha

**Como ativar:**

```
GitHub → Actions → "Setup VPS - first-time" → Run workflow
```

Pode marcar "Pular SSL HMG" se o cert HMG ja existir. O workflow e idempotente.
Apos esta execucao unica, todos os deploys subsequentes atualizarao o Nginx automaticamente.

> Se preferir ativar manualmente na VPS:
> ```bash
> sudo bash /opt/arch-analyzer/prod/.vps/setup-vps.sh SEU_EMAIL
> ```

---

## Fluxo de primeiro setup (passo a passo)

```
1. DNS     : criar registro A  archanalyzer.brunoretiro.com.br    → IP da VPS
             criar registro A  archanalyzerhmg.brunoretiro.com.br → IP da VPS

2. GitHub  : configurar todos os Secrets e Variables listados acima

3. Setup   : acionar o workflow "Setup VPS - first-time" no GitHub Actions
             GitHub → Actions → "Setup VPS - first-time" → Run workflow
             - Instala automaticamente: Docker, Kind, kubectl, KEDA, Nginx, SSL, Portainer, Headlamp
             - Se o DNS do dominio HMG ainda nao propagou: marcar "Pular SSL HMG"

4. Deploy  : push na branch main → deploy automatico em producao (namespace arch-prod)
             push na branch hmg  → deploy automatico em homologacao (namespace arch-hmg)
```

### Opcoes do workflow "Setup VPS - first-time"

| Input | Padrao | Quando usar |
|---|---|---|
| Pular SSL HMG | false | DNS de `archanalyzerhmg` ainda nao propagou |
| Pular verificacao DNS | false | Tem certeza que o DNS esta correto |
| Recriar .env | true | Sempre recria o `.env` de docker-compose |

### O workflow detecta o que ja esta instalado

O "Setup VPS - first-time" verifica se o Kind ja esta instalado antes de rodar o `setup-vps.sh`.
Pode ser acionado novamente a qualquer momento sem risco de duplicacao.

---

## Permissoes de diretorio na VPS

O `setup-vps.yml` cria os diretorios `/opt/arch-analyzer/prod` e `/opt/arch-analyzer/hmg`
como root e transfere a propriedade para o usuario SSH automaticamente.

Se precisar corrigir manualmente:

```bash
# Na VPS, substitua SEU_USUARIO pelo valor do secret VPS_USER
sudo chown -R SEU_USUARIO:SEU_USUARIO /opt/arch-analyzer
```

---

## Solucao de problemas comuns

### SSH: `ssh: no key found`
O secret `VPS_SSH_KEY` esta vazio ou com formato invalido.
Recriar o secret colando o conteudo completo da chave privada (incluindo header e footer).

### SSH: `attempted methods [publickey], no supported methods remain`
A chave publica nao esta no `authorized_keys` da VPS para o `VPS_USER`.
```bash
ssh-copy-id -i ~/.ssh/deploy_key.pub VPS_USER@VPS_HOST
```

### SCP falha com `permission denied`
O usuario SSH nao tem permissao de escrita em `/tmp/` na VPS (improvavel).
Verificar se o `VPS_USER` consegue escrever em `/tmp/`:
```bash
ssh VPS_USER@VPS_HOST "touch /tmp/test && rm /tmp/test && echo ok"
```

### kubectl: `dial tcp [::1]:8080: connect: connection refused`
O cluster Kind nao esta instalado ou nao esta rodando. Solucao: acionar o workflow
"Setup VPS - first-time" ou rodar na VPS:
```bash
sudo bash /opt/arch-analyzer/prod/.vps/setup-vps.sh SEU_EMAIL
```

### kubectl: `error validating data: failed to download openapi`
O pipeline ja usa `--validate=false` em todos os `kubectl apply`. Se aparecer em execucao manual:
```bash
kubectl apply --validate=false -f manifest.yaml
```

### Deploy falha com "namespace not found"
```bash
kubectl create namespace arch-prod
kubectl create namespace arch-hmg
```

### Nginx retorna 502 Bad Gateway
```bash
# Verificar se o socat esta rodando para a porta correta
ss -tlnp | grep 3008
# Verificar se os pods estao rodando
kubectl get pods -n arch-prod
# Recriar o socat manualmente se necessario
~/.socat-30080.sh
```

### GHCR: 403 Forbidden ao escalar pods com KEDA
O `GITHUB_TOKEN` expira ao fim do workflow. Configurar o secret `GHCR_PAT`
(PAT com escopo `read:packages`) conforme a secao 3 acima.

### GHCR: permission denied ao fazer pull manual
```bash
# Usar o GHCR_PAT para autenticar manualmente
echo "ghp_SEU_GHCR_PAT" | docker login ghcr.io -u SEU_USUARIO --password-stdin
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io --docker-username=SEU_USUARIO \
  --docker-password=ghp_SEU_GHCR_PAT -n arch-prod --dry-run=client -o yaml | kubectl apply -f -
```

### KEDA nao esta escalando
```bash
# Verificar estado do ScaledObject
kubectl describe scaledobject ai-service-scaler -n arch-prod
# Verificar se a fila existe no RabbitMQ
kubectl exec -n arch-prod statefulset/rabbitmq -- rabbitmqctl list_queues
```

### Ver logs dos servicos
```bash
kubectl logs -n arch-prod deployment/ai-service --follow
kubectl logs -n arch-prod deployment/upload-service --tail=50
kubectl logs -n arch-prod deployment/frontend --tail=50
# Ver eventos de um pod com problema
kubectl describe pod -n arch-prod -l app=ai-service
```

### Verificar status geral
```bash
kubectl get pods -n arch-prod -o wide
kubectl get pods -n arch-hmg -o wide
kubectl get hpa -n arch-prod
```
