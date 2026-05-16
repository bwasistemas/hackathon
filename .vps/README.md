# Scripts `.vps/` — Setup e Manutencao da VPS

Scripts de infraestrutura para configuracao inicial e manutencao da VPS onde roda o Arch Analyzer.

> **Importante:** estes scripts sao usados apenas para setup da maquina.
> O pipeline de deploy dia-a-dia (`deploy.yml`) **nao chama nenhum script aqui** —
> ele copia os manifests via SCP e aplica com `kubectl` diretamente.

---

## Quando cada script e chamado

### Primeiro setup — workflow `setup-vps.yml` (acionado manualmente)

```
GitHub Actions: "Setup VPS - first-time"
     │
     └─ SSH na VPS
          │
          ├─ [se Kind nao estiver instalado]
          │    └─ setup-vps.sh        Instala toda a infraestrutura da maquina
          │
          └─ setup-deploy.sh          Configura CD (chama os scripts abaixo em sequencia)
               ├─ setup-dirs.sh       Clona/atualiza repositorio em /opt/arch-analyzer/
               ├─ setup-env.sh        Cria .env para docker-compose local
               ├─ setup-nginx.sh      Aplica nginx-archanalyzer.conf
               └─ setup-ssl-hmg.sh   Gera SSL para o dominio de homologacao
```

### Deploy continuo — workflow `deploy.yml` (a cada push)

O `deploy.yml` **nao usa estes scripts**. Ele faz:
1. Checkout no runner
2. SCP dos manifests `infrastructure/k8s/` para a VPS
3. SSH: `kubectl apply` com os manifests copiados

---

## Arquivos

### `lib.sh`

Biblioteca compartilhada. Carregada via `source "$(dirname "$0")/lib.sh"` pelos outros scripts.

Fornece:
- Cores e formatacao no terminal (`RED`, `GREEN`, `CYAN`, etc.)
- Funcoes de log: `ok()`, `err()`, `wrn()`, `inf()`, `hdr()`, `step()`
- `require_root()` — aborta se o script nao estiver rodando como root

---

### `setup-vps.sh`

Instalador completo da VPS. Executado **uma vez** no primeiro setup.

O que instala e configura:
- Docker Engine
- Kind (Kubernetes in Docker) — cria cluster com portas mapeadas: 30080 (prod), 30081 (hmg), 30443, 30444
- kubectl, Helm
- KEDA v2.14 (autoscaler)
- Nginx + certbot (SSL Let's Encrypt para o dominio de producao)
- Portainer (UI Docker, acessivel em `/portainer/`)
- Headlamp (UI Kubernetes, acessivel em `/k8s/`)
- socat (encaminhamento de NodePorts do Kind para o host)

Chamado por: `setup-vps.yml` (se o Kind nao estiver instalado).
Uso manual: `sudo bash setup-vps.sh <email>`

---

### `setup-deploy.sh`

Orquestrador de CD. Chama os outros scripts em sequencia:
`setup-dirs.sh` → `setup-env.sh` → `setup-nginx.sh` → `setup-ssl-hmg.sh`

Aceita as flags `--non-interactive`, `--skip-ssl-hmg`, `--skip-dns-check`, `--force-env`.
Chamado por: `setup-vps.yml` (sempre, apos o setup-vps.sh).
Uso manual: `sudo bash setup-deploy.sh --email SEU_EMAIL [flags]`

---

### `setup-dirs.sh`

Clona ou atualiza o repositorio nos dois diretorios de deploy:
- `/opt/arch-analyzer/prod/` ← branch `main`
- `/opt/arch-analyzer/hmg/`  ← branch `hmg`

Os scripts `.vps/` ficam em `prod/.vps/` e sao o ponto de entrada para todos os
outros scripts (caminho absoluto: `/opt/arch-analyzer/prod/.vps/`).

Chamado por: `setup-deploy.sh`.
Uso manual: `sudo bash setup-dirs.sh [--token GITHUB_PAT]`

---

### `setup-env.sh`

Cria os arquivos `.env` para uso com `docker compose up` local:
- `/opt/arch-analyzer/prod/infrastructure/.env`
- `/opt/arch-analyzer/hmg/infrastructure/.env`

> **Nao e usado pelo pipeline Kubernetes.**
> O `deploy.yml` cria os Kubernetes Secrets diretamente via `kubectl create secret`
> com os valores dos GitHub Secrets. O `.env` serve apenas para desenvolvimento
> local com Docker Compose.

Chamado por: `setup-deploy.sh`.
Uso manual: `sudo bash setup-env.sh [--non-interactive] [--force]`

---

### `setup-nginx.sh`

Aplica o template `nginx-archanalyzer.conf` no Nginx:
1. Substitui `__DOMAIN_PROD__` e `__DOMAIN_HMG__` pelos dominios reais
2. Copia para `/etc/nginx/sites-available/arch-analyzer`
3. Cria symlink em `sites-enabled/`
4. Testa configuracao e recarrega o Nginx

Com `--with-hmg`: inclui o bloco HTTPS de homologacao (requer certificado ja gerado).
Sem a flag: aplica apenas o bloco de producao.
Desativa o site `default` do Nginx para evitar conflito de `default_server` com `arch-analyzer`.

Chamado por: `setup-deploy.sh` e `setup-ssl-hmg.sh` (com `--with-hmg`).
Uso manual: `sudo bash setup-nginx.sh [--with-hmg]`

---

### `setup-ssl-hmg.sh`

Gera o certificado Let's Encrypt para o dominio de homologacao via certbot.
Verifica a propagacao DNS antes de tentar (pode pular com `--skip-dns-check`).
Ao final, chama `setup-nginx.sh --with-hmg` para ativar o bloco HTTPS.

Chamado por: `setup-deploy.sh`.
Uso manual: `sudo bash setup-ssl-hmg.sh EMAIL [--skip-dns-check] [--force]`

---

### `nginx-archanalyzer.conf`

Template de configuracao do Nginx. **Nao aplicado diretamente** — o `setup-nginx.sh`
substitui os placeholders `__DOMAIN_PROD__` e `__DOMAIN_HMG__` antes de instalar.

Rotas configuradas:

| Path | Backend | Porta |
|---|---|---|
| `/` (prod) | frontend prod | NodePort 30080 |
| `/portainer/` (prod) | Portainer Docker | 9000 |
| `/k8s/` (prod) | Headlamp | NodePort 30444 |
| `/grafana/` (prod) | Grafana prod | NodePort 30082 |
| `/prometheus/` (prod) | Prometheus prod | NodePort 30084 (rewrite de prefixo) |
| `/rabbitmq/` (prod) | RabbitMQ management prod | NodePort 30086 |
| `/` (hmg) | frontend hmg | NodePort 30081 |
| `/grafana/` (hmg) | Grafana hmg | NodePort 30083 |
| `/prometheus/` (hmg) | Prometheus hmg | NodePort 30085 (rewrite de prefixo) |
| `/rabbitmq/` (hmg) | RabbitMQ management hmg | NodePort 30087 |

---

### `fix-vps.sh`

Script de correcao pontual para clusters Kind criados sem mapeamento de porta 30444.
Recria o socat para redirecionar `host:30444 → kind-control-plane:30444` (Headlamp).
Usado manualmente quando o Headlamp nao esta acessivel apos instalacao antiga.

Uso manual: `sudo bash fix-vps.sh <dominio>`

---

### `uninstall-vps.sh`

Remove tudo que o `setup-vps.sh` instalou: cluster Kind, containers Docker,
Portainer, Headlamp, Helm, config Nginx, certificados Let's Encrypt, socat.
Usado para reset completo da VPS antes de reinstalar do zero.

Uso manual: `sudo bash uninstall-vps.sh`

---

### `GUIA-CD.md`

Documentacao completa do pipeline: arquitetura, secrets, variaveis GitHub,
fluxo de primeiro setup e solucao de problemas. Leitura recomendada antes
de qualquer intervencao manual na VPS.
