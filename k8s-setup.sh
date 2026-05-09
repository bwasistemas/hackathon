#!/bin/bash

# ============================================
# Arch Analyzer - K8s Setup com Kind
# Sobe o cluster Kubernetes local usando Kind,
# Portainer e Headlamp no servidor
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLUSTER_NAME="arch-analyzer"
NAMESPACE="arch-analyzer"

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $1"; }

show_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║   Arch Analyzer — Kubernetes Setup (Kind)                   ║"
    echo "║   Cluster: arch-analyzer  |  Namespace: arch-analyzer       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

# ─── Pré-requisitos ─────────────────────────────────────────────────────────

check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker não encontrado. Instale: https://docs.docker.com/engine/install/"
        exit 1
    fi
    if ! docker info &>/dev/null; then
        log_error "Docker daemon não está rodando. Execute: sudo systemctl start docker"
        exit 1
    fi
    log_success "Docker: $(docker --version)"
}

install_kind() {
    if command -v kind &>/dev/null; then
        log_success "kind: $(kind version)"
        return
    fi
    log_info "Instalando kind..."
    local arch
    arch=$(uname -m)
    [[ "$arch" == "x86_64" ]] && arch="amd64"
    [[ "$arch" == "aarch64" ]] && arch="arm64"
    curl -Lo /usr/local/bin/kind \
        "https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-${arch}"
    chmod +x /usr/local/bin/kind
    log_success "kind instalado: $(kind version)"
}

install_kubectl() {
    if command -v kubectl &>/dev/null; then
        log_success "kubectl: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"
        return
    fi
    log_info "Instalando kubectl..."
    local arch
    arch=$(uname -m)
    [[ "$arch" == "x86_64" ]] && arch="amd64"
    [[ "$arch" == "aarch64" ]] && arch="arm64"
    local version
    version=$(curl -sSL https://dl.k8s.io/release/stable.txt)
    curl -Lo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${version}/bin/linux/${arch}/kubectl"
    chmod +x /usr/local/bin/kubectl
    log_success "kubectl instalado"
}

# ─── Cluster Kind ────────────────────────────────────────────────────────────

create_cluster() {
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_warning "Cluster '${CLUSTER_NAME}' já existe. Pulando criação."
        return
    fi
    log_info "Criando cluster Kind '${CLUSTER_NAME}'..."
    kind create cluster \
        --name "${CLUSTER_NAME}" \
        --config "${ROOT_DIR}/k8s/kind-config.yaml" \
        --wait 120s
    log_success "Cluster criado!"
}

set_kubectl_context() {
    kubectl config use-context "kind-${CLUSTER_NAME}"
    log_success "Contexto kubectl: kind-${CLUSTER_NAME}"
}

# ─── Nginx Ingress Controller ────────────────────────────────────────────────

deploy_ingress_controller() {
    log_info "Deployando nginx ingress controller (versão Kind)..."
    kubectl apply -f \
        https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

    log_info "Aguardando nginx ingress ficar pronto (até 3 min)..."
    kubectl wait \
        --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=180s
    log_success "nginx ingress pronto!"
}

# ─── Build e carga das imagens ───────────────────────────────────────────────

build_and_load_images() {
    log_info "Construindo imagens Docker dos serviços..."

    docker build -t arch-analyzer/upload-service:local \
        "${ROOT_DIR}/services/upload-service"
    docker build -t arch-analyzer/ai-service:local \
        "${ROOT_DIR}/services/ai-service"
    docker build -t arch-analyzer/report-service:local \
        "${ROOT_DIR}/services/report-service"
    docker build -t arch-analyzer/frontend:local \
        "${ROOT_DIR}/frontend"

    log_success "Imagens construídas!"

    log_info "Carregando imagens no cluster Kind..."
    for img in upload-service ai-service report-service frontend; do
        kind load docker-image \
            "arch-analyzer/${img}:local" \
            --name "${CLUSTER_NAME}"
        log_success "  → arch-analyzer/${img}:local carregada"
    done
}

# ─── Manifests K8s ───────────────────────────────────────────────────────────

apply_manifests() {
    log_info "Aplicando manifests Kubernetes..."

    kubectl apply -f "${ROOT_DIR}/k8s/manifests/00-namespace.yaml"
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/02-secrets.yaml"
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/01-configmaps.yaml"

    # ── Infra: sobe tudo e aguarda cada um estar realmente pronto ───────────
    log_info "  Infraestrutura (postgres, rabbitmq, minio)..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/infra/"

    log_info "  Aguardando postgres..."
    kubectl wait -n "${NAMESPACE}" \
        --for=condition=ready pod --selector=app=postgres \
        --timeout=120s
    log_success "  postgres pronto"

    log_info "  Aguardando minio..."
    kubectl wait -n "${NAMESPACE}" \
        --for=condition=ready pod --selector=app=minio \
        --timeout=120s
    log_success "  minio pronto"

    # RabbitMQ demora mais para inicializar o management plugin após o pod
    # ficar ready — aguardamos a readiness probe passar E damos um buffer extra
    log_info "  Aguardando rabbitmq (pode levar ~60s)..."
    kubectl wait -n "${NAMESPACE}" \
        --for=condition=ready pod --selector=app=rabbitmq \
        --timeout=180s
    log_info "  RabbitMQ pod ready. Aguardando management plugin inicializar..."
    sleep 15
    log_success "  rabbitmq pronto"

    # ── App services: só sobem depois que toda a infra está healthy ─────────
    log_info "  Serviços da aplicação..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/services/"

    log_info "  Aguardando app services subirem..."
    for svc in upload-service ai-service report-service frontend; do
        kubectl rollout status deployment/"${svc}" \
            -n "${NAMESPACE}" --timeout=180s
    done

    # Restart explícito garante que upload-service e ai-service conectam ao
    # RabbitMQ com ele 100% pronto — evita o NullPublisher no primeiro upload
    log_info "  Reconectando serviços ao RabbitMQ (restart rápido)..."
    kubectl rollout restart deployment/upload-service -n "${NAMESPACE}"
    kubectl rollout restart deployment/ai-service -n "${NAMESPACE}"
    kubectl rollout status deployment/upload-service -n "${NAMESPACE}" --timeout=120s
    kubectl rollout status deployment/ai-service -n "${NAMESPACE}" --timeout=120s
    log_success "  Serviços da aplicação prontos e conectados"

    # ── Monitoring e ferramentas ─────────────────────────────────────────────
    log_info "  Monitoramento (prometheus, loki, promtail, grafana)..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/monitoring/"

    log_info "  Ferramentas (headlamp)..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/tools/"

    log_info "  Ingress rules..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/ingress.yaml"

    log_success "Todos os manifests aplicados!"
}

# ─── Portainer ───────────────────────────────────────────────────────────────

deploy_portainer() {
    log_info "Subindo Portainer (container Docker standalone)..."

    if docker ps -a --format '{{.Names}}' | grep -q "^portainer$"; then
        log_warning "Container 'portainer' já existe. Pulando."
        log_info "  Se precisar resetar: sudo ./k8s-setup.sh reset-portainer"
        return
    fi

    docker volume create portainer_data 2>/dev/null || true

    docker run -d \
        --name portainer \
        --restart=unless-stopped \
        -p 9000:9000 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v portainer_data:/data \
        portainer/portainer-ce:latest

    log_success "Portainer iniciado → http://$(hostname -I | awk '{print $1}'):9000"
    log_info "  Acesse e crie o usuário admin na primeira vez (5 min para configurar)"
}

reset_portainer() {
    log_warning "Removendo dados antigos do Portainer..."
    docker stop portainer 2>/dev/null || true
    docker rm portainer 2>/dev/null || true
    docker volume rm portainer_data 2>/dev/null || true
    deploy_portainer
    log_success "Portainer resetado — crie novo admin em http://$(hostname -I | awk '{print $1}'):9000"
}

# ─── Aguardar todos os deployments ──────────────────────────────────────────

wait_all_deployments() {
    log_info "Verificando deployments de monitoramento (até 5 min)..."

    local deployments=(prometheus grafana loki headlamp)

    for dep in "${deployments[@]}"; do
        kubectl rollout status deployment/"${dep}" \
            -n "${NAMESPACE}" \
            --timeout=300s || log_warning "  ${dep} ainda inicializando (normal no primeiro boot)"
    done
}

# ─── Status final ────────────────────────────────────────────────────────────

show_status() {
    local host_ip
    host_ip=$(hostname -I | awk '{print $1}')

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                  CLUSTER PRONTO — ACESSO                    ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                              ║"
    echo "║  🌐 Frontend (app principal)  → http://${host_ip}           "
    echo "║  📉 Grafana                   → http://${host_ip}:3000      "
    echo "║     login: fiap / fiap                                      ║"
    echo "║  📈 Prometheus                → http://${host_ip}:9090      "
    echo "║  🐰 RabbitMQ management       → http://${host_ip}:15672     "
    echo "║     login: fiap / fiap                                      ║"
    echo "║  🗄️  MinIO console             → http://${host_ip}:9002      "
    echo "║     login: fiap / fiap1234                                  ║"
    echo "║  🪖 Headlamp (K8s UI)         → http://${host_ip}:4466      "
    echo "║  🐳 Portainer (Docker+K8s UI) → http://${host_ip}:9000      "
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    log_info "Pods no namespace ${NAMESPACE}:"
    kubectl get pods -n "${NAMESPACE}"
    echo ""
    log_info "Token para o Headlamp:"
    kubectl create token headlamp -n "${NAMESPACE}" 2>/dev/null || \
        echo "  Execute: kubectl create token headlamp -n ${NAMESPACE}"
}

# ─── Comandos ────────────────────────────────────────────────────────────────

cmd_start() {
    show_banner
    check_docker
    install_kind
    install_kubectl
    create_cluster
    set_kubectl_context
    deploy_ingress_controller
    build_and_load_images
    apply_manifests
    deploy_portainer
    wait_all_deployments
    show_status
}

cmd_stop() {
    show_banner
    log_info "Deletando cluster Kind '${CLUSTER_NAME}'..."
    kind delete cluster --name "${CLUSTER_NAME}" || true
    log_info "Parando Portainer..."
    docker stop portainer 2>/dev/null || true
    docker rm portainer 2>/dev/null || true
    log_success "Tudo parado!"
}

cmd_status() {
    set_kubectl_context 2>/dev/null || true
    echo ""
    kubectl get pods -n "${NAMESPACE}" 2>/dev/null || echo "Cluster não encontrado."
    echo ""
    kubectl get svc -n "${NAMESPACE}" 2>/dev/null || true
}

cmd_logs() {
    local svc="${2:-frontend}"
    set_kubectl_context
    kubectl logs -n "${NAMESPACE}" -l "app=${svc}" --tail=100 -f
}

cmd_reload_images() {
    show_banner
    set_kubectl_context
    build_and_load_images
    log_info "Reiniciando deployments dos serviços..."
    for svc in upload-service ai-service report-service frontend; do
        kubectl rollout restart deployment/"${svc}" -n "${NAMESPACE}"
    done
    for svc in upload-service ai-service report-service frontend; do
        kubectl rollout status deployment/"${svc}" -n "${NAMESPACE}" --timeout=120s
    done
    log_success "Imagens recarregadas e serviços reiniciados!"
}

# Reprocessa um upload que ficou preso em RECEIVED
# Uso: ./k8s-setup.sh reprocess <upload_id>
cmd_reprocess() {
    local upload_id="${2:-}"
    if [[ -z "$upload_id" ]]; then
        log_error "Informe o upload_id. Ex: ./k8s-setup.sh reprocess <uuid>"
        log_info  "Para listar uploads pendentes:"
        echo "  kubectl exec -n ${NAMESPACE} deploy/postgres -- \\"
        echo "    psql -U fiap -d fiap -c \"SELECT id, filename, status FROM uploads WHERE status='RECEIVED';\""
        exit 1
    fi

    set_kubectl_context

    log_info "Buscando dados do upload ${upload_id} no banco..."
    local row
    row=$(kubectl exec -n "${NAMESPACE}" deploy/postgres -- \
        psql -U fiap -d fiap -tA -c \
        "SELECT filename, file_path, content_type FROM uploads WHERE id='${upload_id}';" 2>/dev/null)

    if [[ -z "$row" ]]; then
        log_error "Upload não encontrado: ${upload_id}"
        exit 1
    fi

    local filename file_path content_type
    filename=$(echo "$row"    | cut -d'|' -f1)
    file_path=$(echo "$row"   | cut -d'|' -f2)
    content_type=$(echo "$row" | cut -d'|' -f3)

    log_info "Publicando na fila: ${filename}"

    kubectl exec -n "${NAMESPACE}" deploy/upload-service -- python3 -c "
import asyncio, aio_pika, json

async def publish():
    conn = await aio_pika.connect_robust(host='rabbitmq', port=5672, login='fiap', password='fiap')
    ch = await conn.channel()
    body = json.dumps({
        'upload_id': '${upload_id}',
        'filename': '${filename}',
        'file_path': '${file_path}',
        'content_type': '${content_type}'
    })
    await ch.default_exchange.publish(
        aio_pika.Message(body=body.encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key='diagram.upload'
    )
    await conn.close()
    print('Mensagem publicada!')

asyncio.run(publish())
"
    log_success "Upload ${upload_id} reenviado para a fila!"
    log_info "Acompanhe: ./k8s-setup.sh logs ai-service"
}

show_help() {
    echo ""
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos:"
    echo "  start               Sobe o cluster Kind + todos os serviços (padrão)"
    echo "  stop                Destrói o cluster e para o Portainer"
    echo "  status              Mostra status dos pods e services"
    echo "  logs [serviço]      Stream de logs (padrão: frontend)"
    echo "  reload              Reconstrói e recarrega imagens locais no cluster"
    echo "  reprocess <uuid>    Recoloca um upload preso em RECEIVED de volta na fila"
    echo "  reset-portainer     Apaga dados do Portainer e recria do zero"
    echo "  help                Esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  ./k8s-setup.sh logs ai-service"
    echo "  ./k8s-setup.sh reprocess 4a1795c1-2fb9-4aa1-b04e-560c7231cddb"
    echo ""
}

main() {
    case "${1:-start}" in
        start)           cmd_start ;;
        stop)            cmd_stop ;;
        status)          cmd_status ;;
        logs)            cmd_logs "$@" ;;
        reload)          cmd_reload_images ;;
        reprocess)       cmd_reprocess "$@" ;;
        reset-portainer) reset_portainer ;;
        help|--help|-h)  show_help ;;
        *) log_error "Comando desconhecido: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
