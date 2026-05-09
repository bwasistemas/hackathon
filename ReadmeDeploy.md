# Deploy com Kubernetes (Kind) — Arch Analyzer

Este documento explica como funciona o deploy do Arch Analyzer em um servidor Linux usando **Kind** (Kubernetes in Docker), com **Portainer** e **Headlamp** para visualização da infra.

---

## O que é cada ferramenta?

| Ferramenta | O que faz |
|---|---|
| **Docker** | Cria e executa containers isolados. Base de tudo. |
| **Kind** | "Kubernetes in Docker" — sobe um cluster K8s inteiro dentro de containers Docker. Ideal para testes locais. |
| **kubectl** | CLI para interagir com o cluster K8s (deploy, logs, status...). |
| **nginx Ingress** | Funciona como um "porteiro" do cluster: recebe requisições HTTP na porta 80 e roteia para o serviço correto. |
| **Portainer** | UI web para gerenciar containers Docker e ambientes K8s. Roda fora do Kind, como container Docker normal. |
| **Headlamp** | Dashboard web nativo de K8s — mostra pods, deployments, logs, tudo no browser. Roda dentro do cluster. |

---

## Estrutura de arquivos criada

```
k8s/
├── kind-config.yaml              # Configuração do cluster Kind (portas, nós)
└── manifests/
    ├── 00-namespace.yaml         # Namespace "arch-analyzer"
    ├── 01-configmaps.yaml        # Configs: prometheus, loki, promtail, grafana
    ├── 02-secrets.yaml           # Senhas e API keys (preencher OPENAI_API_KEY)
    ├── infra/
    │   ├── postgres.yaml         # Banco de dados PostgreSQL
    │   ├── rabbitmq.yaml         # Fila de mensagens RabbitMQ
    │   └── minio.yaml            # Storage de objetos MinIO (como S3)
    ├── services/
    │   ├── upload-service.yaml   # API de upload de diagramas
    │   ├── ai-service.yaml       # Serviço de análise com IA
    │   ├── report-service.yaml   # Serviço de relatórios
    │   └── frontend.yaml         # SPA com nginx interno
    ├── monitoring/
    │   ├── prometheus.yaml       # Coleta de métricas
    │   ├── loki.yaml             # Armazenamento de logs
    │   ├── promtail.yaml         # Agente coletor de logs dos pods
    │   └── grafana.yaml          # Dashboards de monitoramento
    ├── tools/
    │   └── headlamp.yaml         # Dashboard K8s
    └── ingress.yaml              # Regras de roteamento HTTP (porta 80)

k8s-setup.sh                      # Script principal que orquestra tudo
```

---

## Como o cluster funciona por dentro

```
Internet / rede local
        │
        ▼ porta 80
┌──────────────────────────────────────────────────────┐
│  Servidor Linux (192.168.3.2)                        │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │  Kind Cluster (container Docker)            │     │
│  │                                             │     │
│  │  nginx Ingress Controller                   │     │
│  │      └─→ frontend:8051  ←── nginx proxy ──→ upload-service:8001
│  │                                             │     ├─→ report-service:8004
│  │  Monitoring (NodePort)                      │     │
│  │      prometheus:9090  → porta 9090          │     │
│  │      grafana:3000     → porta 3000          │     │
│  │      rabbitmq-ui:15672→ porta 15672         │     │
│  │      minio-console:9001→ porta 9002         │     │
│  │      headlamp:4466    → porta 4466          │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  Portainer (container Docker, fora do Kind)          │
│      porta 9000 → UI web                            │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Por que o frontend consegue falar com upload-service e report-service?

O `nginx.conf` do frontend tem:
```nginx
location /api/v1/upload {
    proxy_pass http://upload-service:8001/upload;
}
```

No Kubernetes, cada Service cria um DNS automático: `upload-service.arch-analyzer.svc.cluster.local`. O nginx dentro do pod do frontend resolve esse nome via DNS interno do K8s — exatamente como funcionava no Docker Compose. Nenhuma mudança de código necessária.

---

## Pré-requisitos no servidor (192.168.3.2 / Contabo)

O servidor precisa ter apenas:
- **Docker** instalado e rodando
- Acesso à internet (para baixar kind, kubectl, imagens)
- Portas liberadas: `80`, `443`, `3000`, `9000`, `9001`, `9002`, `9090`, `15672`, `4466`

O script `k8s-setup.sh start` instala kind e kubectl automaticamente se não estiverem presentes.

---

## Passo a passo para rodar

### 1. Clonar o repositório no servidor

```bash
git clone <url-do-repo> arch-analyzer
cd arch-analyzer
git checkout deploy_test
```

### 2. Preencher a chave da OpenAI

Edite o arquivo de secrets antes de rodar:

```bash
nano k8s/manifests/02-secrets.yaml
```

Altere a linha:
```yaml
  OPENAI_API_KEY: ""
```
Para:
```yaml
  OPENAI_API_KEY: "sk-sua-chave-aqui"
```

> Você também pode copiar do `.env` local que já tem as outras variáveis preenchidas.

### 3. Rodar o setup

```bash
chmod +x k8s-setup.sh
sudo ./k8s-setup.sh start
```

O script vai:
1. Verificar e instalar kind + kubectl
2. Criar o cluster Kind com as portas mapeadas
3. Instalar o nginx Ingress Controller
4. Fazer o build das 4 imagens Docker locais
5. Carregar as imagens no cluster Kind (`kind load docker-image`)
6. Aplicar todos os manifests K8s em ordem
7. Subir o Portainer como container Docker separado
8. Aguardar todos os pods ficarem prontos
9. Exibir as URLs de acesso

---

## URLs de acesso (após o deploy)

| Serviço | URL | Login |
|---|---|---|
| **Frontend (app)** | http://192.168.3.2 | — |
| **Grafana** | http://192.168.3.2:3000 | fiap / fiap |
| **Prometheus** | http://192.168.3.2:9090 | — |
| **RabbitMQ UI** | http://192.168.3.2:15672 | fiap / fiap |
| **MinIO Console** | http://192.168.3.2:9002 | fiap / fiap1234 |
| **Headlamp (K8s)** | http://192.168.3.2:4466 | token (ver abaixo) |
| **Portainer** | http://192.168.3.2:9000 | criar na 1ª vez |

### Obter token para o Headlamp

```bash
kubectl create token headlamp -n arch-analyzer
```

Cole o token gerado no Headlamp ao abrir no browser.

---

## Comandos úteis do k8s-setup.sh

```bash
# Subir tudo
sudo ./k8s-setup.sh start

# Ver status dos pods
sudo ./k8s-setup.sh status

# Ver logs de um serviço (padrão: frontend)
sudo ./k8s-setup.sh logs ai-service

# Rebuildar e recarregar imagens locais (após alterar código)
sudo ./k8s-setup.sh reload

# Derrubar tudo (cluster Kind + Portainer)
sudo ./k8s-setup.sh stop
```

---

## Comandos kubectl diretos

```bash
# Ver todos os pods
kubectl get pods -n arch-analyzer

# Ver logs de um pod específico
kubectl logs -n arch-analyzer deploy/ai-service -f

# Descrever um pod (útil para debugar)
kubectl describe pod -n arch-analyzer -l app=upload-service

# Ver services e portas
kubectl get svc -n arch-analyzer

# Ver ingress
kubectl get ingress -n arch-analyzer

# Reiniciar um deployment (ex: após mudar o secret)
kubectl rollout restart deployment/ai-service -n arch-analyzer
```

---

## Diferença entre Kind e Docker Compose

| Aspecto | Docker Compose | Kind (Kubernetes) |
|---|---|---|
| Orquestração | Docker nativo | Kubernetes |
| Self-healing | Não (restart policy) | Sim (K8s recria pods que caem) |
| Escalabilidade | Manual | `kubectl scale replicas=3` |
| Descoberta de serviços | Nome do container | DNS interno K8s |
| Ingress/Load balancer | Manual | nginx Ingress Controller |
| Config/Secrets | `.env` file | ConfigMap + Secret K8s |
| Ideal para | Dev local rápido | Simular ambiente de produção |

---

## Troubleshooting

**Pod em CrashLoopBackOff:**
```bash
kubectl logs -n arch-analyzer deploy/<nome> --previous
```

**Imagem não encontrada (ErrImageNeverPull):**
```bash
# Recarregar a imagem no Kind
kind load docker-image arch-analyzer/<servico>:local --name arch-analyzer
kubectl rollout restart deployment/<servico> -n arch-analyzer
```

**Porta já em uso no servidor:**
```bash
sudo lsof -i :<porta>
# Parar o processo conflitante ou alterar a porta no kind-config.yaml
```

**Cluster Kind não sobe:**
```bash
kind delete cluster --name arch-analyzer
sudo ./k8s-setup.sh start
```
