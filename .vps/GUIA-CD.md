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
│   ├─ archanalyzerhmg.brunoretiro.com.br/        → Kind NodePort 30081 (arch-hmg)
│   ├─ archanalyzer.brunoretiro.com.br/portainer/ → Portainer :9000
│   └─ archanalyzer.brunoretiro.com.br/k8s/       → Headlamp  :30444
│
├─ Kind cluster (2 workers)
│   ├─ Namespace arch-prod (producao — branch main)
│   │   frontend:30080, upload:8001, ai:8003, report:8004
│   │   postgres:5432, rabbitmq:5672, minio:9000, prometheus:9090, grafana:3000
│   │
│   └─ Namespace arch-hmg (homologacao — branch hmg)
│       frontend:30081 (host), mesmos servicos internos
│
├─ KEDA v2.14 — autoscaling do ai-service
│   ScaledObject: min=1, max=MAX_REPLICAS, trigger=queue diagram.upload
│
└─ Portainer + Headlamp — UIs de gerenciamento
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

---

## Estrutura dos Scripts `.vps/`

| Script | Responsabilidade |
|---|---|
| `setup-vps.sh` | Orquestrador — instala Docker, Kind, kubectl, KEDA, Nginx, SSL, Portainer, Headlamp |
| `setup-deploy.sh` | Orquestrador de CD — clona repo, configura Nginx, gera SSL HMG |
| `setup-dirs.sh` | Clona/atualiza repositorio nos diretorios de deploy e ajusta permissoes |
| `setup-env.sh` | Cria arquivos `.env` para prod e hmg |
| `setup-nginx.sh` | Configura Nginx e recarrega |
| `setup-ssl-hmg.sh` | Gera certificado SSL para `archanalyzerhmg.brunoretiro.com.br` |
| `lib.sh` | Funcoes compartilhadas (logging, cores, utilitarios) |
| `nginx-archanalyzer.conf` | Template Nginx (placeholders substituidos pelo setup-nginx.sh) |

---

## Configuracao de Secrets e Variables no GitHub

Acesse: `github.com/bwasistemas/hackathon → Settings → Secrets and variables → Actions`

---

### 1. Deploy Key SSH para clone na VPS

O pipeline usa SSH para clonar o repositorio na VPS (`git@github.com:bwasistemas/hackathon.git`).
Tokens HTTPS (GITHUB_TOKEN, PAT) nao funcionam confiavelmente de maquinas externas.
A solucao correta e uma chave SSH de deploy.

**Como configurar (uma vez na VPS):**

```bash
# 1. Gerar chave dedicada para o GitHub (na VPS, como o usuario de deploy)
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""

# 2. Exibir a chave publica — copiar o conteudo
cat ~/.ssh/github_deploy.pub

# 3. Configurar SSH para usar essa chave ao acessar github.com
cat >> ~/.ssh/config << 'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  StrictHostKeyChecking no
EOF
chmod 600 ~/.ssh/config

# 4. Testar a autenticacao
ssh -T git@github.com
# Esperado: "Hi bwasistemas/hackathon! You've successfully authenticated..."
```

**Adicionar a chave publica como Deploy Key no GitHub:**

`github.com/bwasistemas/hackathon → Settings → Deploy keys → Add deploy key`
- Title: `VPS Deploy Key`
- Key: colar o conteudo de `~/.ssh/github_deploy.pub`
- Allow write access: **nao** (leitura e suficiente para clone)

Apos isso, os workflows clonam via SSH automaticamente — sem PAT ou GITHUB_TOKEN.

---

### 2. VPS_SSH_KEY — Chave SSH para o CI acessar a VPS

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

### 3. Tabela completa de Secrets

| Secret | Descricao |
|---|---|
| `GH_PAT` | Personal Access Token (escopo `repo`) — para git clone/fetch na VPS |
| `VPS_HOST` | IP publico da VPS |
| `VPS_USER` | Usuario SSH da VPS (`ubuntu`, `root`, etc.) |
| `VPS_SSH_KEY` | Conteudo da chave privada SSH (sem passphrase) |
| `VPS_SSH_PORT` | Porta SSH — omitir se for a padrao 22 |
| `LETSENCRYPT_EMAIL` | Email para notificacoes e renovacao dos certs SSL |
| `POSTGRES_USER` | Usuario do PostgreSQL |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL |
| `RABBITMQ_USER` | Usuario do RabbitMQ |
| `RABBITMQ_PASSWORD` | Senha do RabbitMQ |
| `OPENAI_API_KEY` | Chave da API OpenAI / OpenRouter |
| `JWT_SECRET_KEY` | Chave de assinatura dos JWTs (minimo 48 chars aleatorios) |
| `ADMIN_USER` | Usuario admin da aplicacao |
| `ADMIN_PASSWORD` | Senha do usuario admin da aplicacao |
| `MINIO_ACCESS_KEY` | Usuario root do MinIO (MINIO_ROOT_USER) |
| `MINIO_SECRET_KEY` | Senha root do MinIO (MINIO_ROOT_PASSWORD) |
| `GRAFANA_USER` | Usuario do Grafana |
| `GRAFANA_PASSWORD` | Senha do Grafana |

O pipeline cria/atualiza os Kubernetes Secrets a cada deploy — nao e necessario
rodar `setup-env.sh` manualmente antes do primeiro deploy.

---

### 4. Tabela de Variables (valores nao sensiveis)

Aba **Variables** (nao Secrets) na mesma tela:

| Variable | Padrao | Descricao |
|---|---|---|
| `DOMAIN_PROD` | `archanalyzer.brunoretiro.com.br` | Dominio de producao |
| `DOMAIN_HMG` | `archanalyzerhmg.brunoretiro.com.br` | Dominio de homologacao |
| `MAX_REPLICAS` | `5` | Maximo de replicas do ai-service (KEDA) |
| `QUEUE_MESSAGES_PER_REPLICA` | `5` | Mensagens por replica para escala |
| `POSTGRES_DB` | `fiap` | Nome do banco de dados |
| `MINIO_BUCKET` | `fiap` | Nome do bucket MinIO |
| `TZ` | `America/Sao_Paulo` | Fuso horario dos containers |

---

## Fluxo de primeiro setup (passo a passo)

```
1. DNS     : criar registro A  archanalyzer.brunoretiro.com.br    → IP da VPS
             criar registro A  archanalyzerhmg.brunoretiro.com.br → IP da VPS

2. GitHub  : configurar todos os Secrets e Variables listados acima
             (GH_PAT e VPS_SSH_KEY sao obrigatorios para o pipeline funcionar)

3. Setup   : acionar o workflow "Setup VPS (first-time)" no GitHub Actions
             GitHub → Actions → "Setup VPS (first-time)" → Run workflow
             - Instala automaticamente: Docker, Kind, kubectl, KEDA, Nginx, SSL, Portainer, Headlamp
             - Se o DNS do dominio HMG ainda nao propagou: marcar "Pular SSL HMG"

4. Deploy  : push na branch main → deploy automatico em producao (namespace arch-prod)
             push na branch hmg  → deploy automatico em homologacao (namespace arch-hmg)
```

### Opcoes do workflow "Setup VPS (first-time)"

| Input | Padrao | Quando usar |
|---|---|---|
| Pular SSL HMG | false | DNS de `archanalyzerhmg` ainda nao propagou |
| Pular verificacao DNS | false | Tem certeza que o DNS esta correto |
| Recriar .env | false | Precisa reconfigurar credenciais na VPS |

### O workflow detecta o que ja esta instalado

O "Setup VPS (first-time)" verifica se o Kind ja esta instalado antes de rodar o `setup-vps.sh`.
Pode ser acionado novamente a qualquer momento sem risco de duplicacao.

---

## Permissoes de diretorio na VPS

O pipeline cria os diretorios de deploy em `/opt/arch-analyzer/prod` e `/opt/arch-analyzer/hmg`.
O `setup-dirs.sh` (chamado pelo setup-vps.sh) cria esses diretorios como root e transfere
a propriedade automaticamente para o usuario SSH (`$SUDO_USER`).

Se precisar corrigir manualmente (ex.: diretorio criado antes do fix):

```bash
# Na VPS, substitua SEU_USUARIO pelo valor do secret VPS_USER
sudo chown -R SEU_USUARIO:SEU_USUARIO /opt/arch-analyzer
```

**Por que o deploy nao usa sudo:**
O `mkdir -p "$DEPLOY_DIR"` no pipeline nao usa sudo porque o diretorio pai ja pertence
ao usuario SSH apos o setup. Se aparecer `Permission denied` no mkdir, rode o comando
acima na VPS e re-execute o deploy.

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

### Git clone: `Invalid username or token`
O `GITHUB_TOKEN` automatico do Actions nao funciona para clone em maquinas externas.
Criar um PAT (escopo `repo`) e adicionar como secret `GH_PAT` conforme secao 1 acima.

### mkdir: `Permission denied` em `/opt/arch-analyzer`
O usuario SSH nao tem permissao de escrita no diretorio. Corrigir na VPS:
```bash
sudo chown -R VPS_USER:VPS_USER /opt/arch-analyzer
```

### kubectl: `dial tcp [::1]:8080: connect: connection refused`
O cluster Kind nao esta instalado ou nao esta rodando. Solucao: acionar o workflow
"Setup VPS (first-time)" ou rodar na VPS:
```bash
sudo bash /opt/arch-analyzer/prod/.vps/setup-vps.sh SEU_EMAIL
```

### kubectl: `error validating data: failed to download openapi`
Erro de validacao OpenAPI ao aplicar manifests. O pipeline ja usa `--validate=false`
em todos os `kubectl apply` para contornar isso. Se aparecer em execucao manual:
```bash
kubectl apply --validate=false -f manifest.yaml
```

### Deploy falha com "namespace not found"
```bash
# Criar namespace manualmente:
kubectl create namespace arch-prod
kubectl create namespace arch-hmg
# Depois re-executar o deploy
```

### Nginx retorna 502
```bash
# Verificar se os pods estao rodando:
kubectl get pods -n arch-prod
# Verificar logs do frontend:
kubectl logs -n arch-prod deployment/frontend
```

### GHCR: permission denied ao fazer pull manual
```bash
# O GITHUB_TOKEN expira com o workflow. Para pull manual, usar o GH_PAT:
echo "ghp_SEU_GH_PAT" | docker login ghcr.io -u SEU_USUARIO --password-stdin
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io --docker-username=SEU_USUARIO \
  --docker-password=ghp_SEU_GH_PAT -n arch-prod --dry-run=client -o yaml | kubectl apply -f -
```

### KEDA nao esta escalando
```bash
# Verificar estado do ScaledObject:
kubectl describe scaledobject ai-service-scaler -n arch-prod
# Verificar se a fila existe no RabbitMQ:
kubectl exec -n arch-prod statefulset/rabbitmq -- rabbitmqctl list_queues
```

### Ver logs do ai-service
```bash
kubectl logs -n arch-prod deployment/ai-service --follow
# Verificar autoscaling:
kubectl get hpa -n arch-prod
```
