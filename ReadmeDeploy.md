# Deploy com Kubernetes (Kind) — Arch Analyzer

Deploy do Arch Analyzer em servidor Linux usando **Kind** (Kubernetes in Docker), **nginx Ingress**, **Portainer** e **Headlamp**.

> **Testado em:** Ubuntu 26.04 LTS, Docker 29.1.3, Kind v0.23.0, kubectl v1.36.0

---

## Pré-requisitos no servidor

- **Docker** instalado e rodando (`sudo systemctl start docker`)
- Acesso à internet (para baixar kind, kubectl e imagens)
- Portas liberadas no firewall: `80`, `3000`, `4466`, `9000`, `9002`, `9090`, `15672`

O script instala `kind` e `kubectl` automaticamente se não estiverem presentes.

---

## Passo a passo

### 1. Clonar o repositório

```bash
git clone <url-do-repo> arch-analyzer
cd arch-analyzer
git checkout deploy_test
```

### 2. Preencher a chave da OpenAI/OpenRouter

```bash
nano k8s/manifests/02-secrets.yaml
```

Preencha os campos:
```yaml
  OPENAI_API_KEY: "sk-or-v1-..."
  OPENAI_BASE_URL: "https://openrouter.ai/api/v1"
  LLM_MODEL: "deepseek/deepseek-chat"
  LLM_OCR: "google/gemini-2.0-flash-001"
```

### 3. Rodar o setup

```bash
chmod +x k8s-setup.sh
sudo ./k8s-setup.sh start
```

Tempo estimado: **~10 minutos** (build das imagens + pull do cluster Kind).

O script vai:
1. Instalar `kind` e `kubectl` se necessário
2. Criar o cluster Kind com as portas mapeadas
3. Instalar o nginx Ingress Controller
4. Fazer build das 4 imagens Docker locais
5. Carregar as imagens no Kind (`kind load docker-image`)
6. Aplicar todos os manifests K8s **na ordem correta** — infra primeiro, serviços depois
7. Aguardar RabbitMQ estar 100% pronto antes de subir os serviços
8. Fazer restart de `upload-service` e `ai-service` para garantir conexão limpa com RabbitMQ
9. Subir o Portainer como container Docker separado
10. Exibir as URLs e o token do Headlamp

---

## URLs de acesso

| Serviço | URL | Login |
|---|---|---|
| **Frontend (app)** | `http://<IP>` | — |
| **Grafana** | `http://<IP>:3000` | fiap / fiap |
| **Prometheus** | `http://<IP>:9090` | — |
| **RabbitMQ UI** | `http://<IP>:15672` | fiap / fiap |
| **MinIO Console** | `http://<IP>:9002` | fiap / fiap1234 |
| **Headlamp** | `http://<IP>:4466` | token (gerado no final do script) |
| **Portainer** | `http://<IP>:9000` | criar na 1ª vez |

---

## Portainer — primeiro acesso

Na **primeira vez** o Portainer exibe uma tela de setup. Você tem **5 minutos** para criar o usuário admin. Se o tempo expirar:

```bash
sudo ./k8s-setup.sh reset-portainer
```

Isso apaga os dados antigos e recria o container do zero.

## Headlamp — login com token

O script exibe o token ao final. Para gerar um novo (válido por 24h):

```bash
kubectl create token headlamp -n arch-analyzer --duration=24h
```

Cole o token gerado na tela de login do Headlamp.

---

## Comandos do k8s-setup.sh

```bash
# Subir tudo (primeira vez ou após stop)
sudo ./k8s-setup.sh start

# Ver status dos pods e services
sudo ./k8s-setup.sh status

# Stream de logs de um serviço
sudo ./k8s-setup.sh logs ai-service

# Rebuildar e recarregar imagens após mudar código
sudo ./k8s-setup.sh reload

# Reprocessar um upload preso em RECEIVED
sudo ./k8s-setup.sh reprocess <upload_id>

# Resetar o Portainer (apaga dados e recria)
sudo ./k8s-setup.sh reset-portainer

# Derrubar tudo (cluster Kind + Portainer)
sudo ./k8s-setup.sh stop
```

---

## Comandos kubectl úteis

```bash
# Todos os pods
kubectl get pods -n arch-analyzer

# Logs em tempo real
kubectl logs -n arch-analyzer deploy/ai-service -f

# Descrever pod (útil para erros de startup)
kubectl describe pod -n arch-analyzer -l app=upload-service

# Reiniciar um serviço
kubectl rollout restart deployment/ai-service -n arch-analyzer

# Ver filas do RabbitMQ
kubectl exec -n arch-analyzer deploy/rabbitmq -- \
  rabbitmqctl list_queues name messages consumers state

# Ver uploads no banco
kubectl exec -n arch-analyzer deploy/postgres -- \
  psql -U fiap -d fiap -c "SELECT id, filename, status, created_at FROM uploads ORDER BY created_at DESC LIMIT 10;"
```

---

## Troubleshooting

### Upload fica preso em RECEIVED

Isso acontece quando `upload-service` ou `ai-service` subiram antes do RabbitMQ estar 100% pronto e usaram o `NullPublisher` (fallback sem conexão). O script novo corrige isso com restart automático, mas se acontecer manualmente:

```bash
# 1. Listar uploads presos
kubectl exec -n arch-analyzer deploy/postgres -- \
  psql -U fiap -d fiap -c "SELECT id, filename, status FROM uploads WHERE status='RECEIVED';"

# 2. Reenviar para a fila
sudo ./k8s-setup.sh reprocess <upload_id>
```

### Pod em CrashLoopBackOff

```bash
# Ver logs do container que crashou
kubectl logs -n arch-analyzer deploy/<nome> --previous
```

### Imagem não encontrada (ErrImageNeverPull)

```bash
# Recarregar a imagem no Kind
kind load docker-image arch-analyzer/<servico>:local --name arch-analyzer
kubectl rollout restart deployment/<servico> -n arch-analyzer
```

### Porta já em uso no servidor

```bash
sudo lsof -i :<porta>
# Parar o processo conflitante antes de rodar o setup
```

### Cluster Kind não sobe

```bash
sudo ./k8s-setup.sh stop
sudo ./k8s-setup.sh start
```

---

## Estrutura dos arquivos

```
k8s/
├── kind-config.yaml              # Cluster Kind (portas mapeadas para o host)
└── manifests/
    ├── 00-namespace.yaml         # Namespace "arch-analyzer"
    ├── 01-configmaps.yaml        # Configs: prometheus, loki, promtail, grafana
    ├── 02-secrets.yaml           # Senhas e API keys (preencher antes do deploy)
    ├── infra/
    │   ├── postgres.yaml         # PostgreSQL + PVC
    │   ├── rabbitmq.yaml         # RabbitMQ + PVC (NodePort 15672)
    │   └── minio.yaml            # MinIO + PVC (NodePort 9002)
    ├── services/
    │   ├── upload-service.yaml   # API de upload (imagePullPolicy: Never)
    │   ├── ai-service.yaml       # Serviço de IA (imagePullPolicy: Never)
    │   ├── report-service.yaml   # Serviço de relatórios (imagePullPolicy: Never)
    │   └── frontend.yaml         # SPA nginx (imagePullPolicy: Never)
    ├── monitoring/
    │   ├── prometheus.yaml       # Prometheus + PVC (NodePort 9090)
    │   ├── loki.yaml             # Loki + PVC
    │   ├── promtail.yaml         # DaemonSet + RBAC (lê /var/log/pods)
    │   └── grafana.yaml          # Grafana + PVC (NodePort 3000)
    ├── tools/
    │   └── headlamp.yaml         # Dashboard K8s (NodePort 4466)
    └── ingress.yaml              # Roteamento porta 80 → frontend

k8s-setup.sh                      # Script principal
```

**Por que `imagePullPolicy: Never`?** As imagens da aplicação são construídas localmente e carregadas no Kind com `kind load docker-image`. Esse flag diz ao K8s para nunca tentar baixar do Docker Hub — usa só o que já está no cluster.

---

## Arquitetura resumida

```
Requisição HTTP (porta 80)
        │
        ▼
nginx Ingress Controller (dentro do Kind)
        │
        ▼
frontend:8051  ──nginx proxy──▶  upload-service:8001
                                 report-service:8004

Portas diretas via NodePort:
  :3000  → Grafana
  :9090  → Prometheus
  :15672 → RabbitMQ UI
  :9002  → MinIO Console
  :4466  → Headlamp

Porta Docker (fora do Kind):
  :9000  → Portainer
```
