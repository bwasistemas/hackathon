# Manifests Kubernetes — Arch Analyzer

Estes arquivos sao aplicados em ordem numerica pelo pipeline `deploy.yml` a cada push.
O prefixo numerico garante a ordem correta de criacao (dependencias primeiro).

**Como o pipeline executa:**

```
deploy.yml
  1. actions/checkout           → runner tem os arquivos
  2. appleboy/scp-action        → copia infrastructure/k8s/ para /tmp/arch-k8s-<namespace>/ na VPS
  3. appleboy/ssh-action (SSH)  → envsubst | kubectl apply -n <namespace> *.yaml | sort
```

**Variaveis substituidas em tempo de deploy via `envsubst`:**

| Variavel | Origem |
|---|---|
| `IMAGE_PREFIX` | `ghcr.io/bwasistemas/hackathon` (fixo) |
| `IMAGE_TAG` | `<branch>-<sha>` gerado no job build-push |
| `NAMESPACE` | `arch-prod` (main) ou `arch-hmg` (hmg) |
| `DOMAIN` | `DOMAIN_PROD` ou `DOMAIN_HMG` do GitHub Variables |
| `POSTGRES_DB`, `MINIO_BUCKET`, `TZ` | GitHub Variables |
| `ALLOWED_ORIGINS` | derivado do DOMAIN |
| `FRONTEND_NODEPORT` | 30080 (prod) / 30081 (hmg) |
| `RABBITMQ_MGMT_NODEPORT` | 30086 (prod) / 30087 (hmg) |
| `MAX_REPLICAS`, `QUEUE_MESSAGES_PER_REPLICA` | GitHub Variables |

---

## Arquivos

### `10-configmap.yaml`

Cria o **ConfigMap `arch-config`** com todas as variaveis de configuracao nao sensiveis
compartilhadas entre os pods: host do banco, host do RabbitMQ, endpoint do MinIO, fuso
horario, modelos de LLM, configuracoes de JWT, URL base da OpenAI.

> Deve ser aplicado primeiro pois todos os Deployments referenciam este ConfigMap
> via `configMapKeyRef`.

---

### `20-postgres.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `postgres-data` | PVC 10Gi | Persistencia dos dados |
| `postgres` | Service ClusterIP:5432 | Acesso interno ao banco |
| `postgres` | StatefulSet | Banco de dados principal da aplicacao |

Credenciais via Secret `arch-secrets` (criado pelo pipeline antes do apply).

---

### `30-rabbitmq.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `rabbitmq-data` | PVC 5Gi | Persistencia das filas |
| `rabbitmq-headless` | Service headless | DNS estavel para o StatefulSet |
| `rabbitmq` | Service ClusterIP | AMQP (5672) e management (15672) para outros pods |
| `rabbitmq-management-np` | Service NodePort `${RABBITMQ_MGMT_NODEPORT}` | Expoe o management para o Nginx em `/rabbitmq/` |
| `rabbitmq` | StatefulSet | Broker de mensagens — publica fila `diagram.upload` |

O management usa path prefix `/rabbitmq` configurado via `RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS`.

---

### `40-minio.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `minio-data` | PVC 20Gi | Armazenamento dos arquivos |
| `minio` | Service ClusterIP | API S3 (9000) e console web (9001) — acesso interno |
| `minio` | StatefulSet | Object storage para arquivos de upload e resultados |

Imagem pinada (`RELEASE.2024-07-31T05-46-26Z`) para evitar quebras por atualizacao automatica.

---

### `50-upload-service.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `upload-service` | Service ClusterIP:8001 | Acesso interno |
| `upload-service` | Deployment | Recebe uploads via HTTP, valida, salva no MinIO e publica na fila `diagram.upload` |

---

### `60-ai-service.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `ai-service` | Service ClusterIP:8003 | Acesso interno |
| `ai-service` | Deployment | Consome fila `diagram.upload`, faz OCR e analise com LLM via OpenAI/OpenRouter |

Escala automaticamente via KEDA — as regras estao em `90-keda.yaml`.

---

### `70-report-service.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `report-service` | Service ClusterIP:8004 | Acesso interno |
| `report-service` | Deployment | Gera relatorios PDF a partir das analises do ai-service |

---

### `80-frontend.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `frontend` | Service NodePort `${FRONTEND_NODEPORT}` | Expoe para o Nginx em `/` |
| `frontend` | Deployment | Interface Streamlit da aplicacao |

---

### `90-keda.yaml`

| Recurso | Tipo | Descricao |
|---|---|---|
| `rabbitmq-trigger-auth` | TriggerAuthentication | Referencia ao Secret `rabbitmq-keda-auth` com a URL AMQP |
| `ai-service-scaler` | ScaledObject | Regra de autoscaling do `ai-service` |

Logica de escala: `replicas = ceil(mensagens_na_fila / QUEUE_MESSAGES_PER_REPLICA)`,
minimo 1, maximo `${MAX_REPLICAS}`, cooldown de 60s.

> Requer KEDA instalado no cluster. O pipeline instala automaticamente se os CRDs
> `scaledobjects.keda.sh` nao existirem.

---

## Ordem de dependencias

```
10-configmap
    │
    ├─ 20-postgres        (banco — upload/ai/report dependem)
    ├─ 30-rabbitmq        (fila — upload publica, ai consome, KEDA monitora)
    ├─ 40-minio           (storage — upload e report usam)
    │
    ├─ 50-upload-service  → grava no minio + publica na fila
    ├─ 60-ai-service  ←─ KEDA (90) escala com base na fila
    ├─ 70-report-service  → le do banco + escreve no minio
    ├─ 80-frontend        → proxy para os servicos acima
    │
    └─ 90-keda            (requer KEDA no cluster + rabbitmq rodando)
```

> Observabilidade (Prometheus, Grafana, Loki, Promtail) roda no namespace
> compartilhado **arch-geral** — veja `infrastructure/k8s-geral/`.

## NodePorts por ambiente

| Servico | Producao (arch-prod) | Homologacao (arch-hmg) |
|---|---|---|
| frontend | 30080 | 30081 |
| rabbitmq-management | 30086 | 30087 |

Grafana (30082) e Prometheus (30084) sao compartilhados via namespace arch-geral.
