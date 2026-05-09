#!/bin/bash

# ============================================
# Arch Analyzer - K8s Setup com Kind
# Sobe o cluster Kubernetes local usando Kind,
# Portainer e Headlamp no servidor 192.168.3.2
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

    log_info "  Infraestrutura (postgres, rabbitmq, minio)..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/infra/"

    log_info "  Aguardando postgres ficar pronto..."
    kubectl wait \
        -n "${NAMESPACE}" \
        --for=condition=ready pod \
        --selector=app=postgres \
        --timeout=120s

    log_info "  Aguardando rabbitmq ficar pronto..."
    kubectl wait \
        -n "${NAMESPACE}" \
        --for=condition=ready pod \
        --selector=app=rabbitmq \
        --timeout=120s

    log_info "  Aguardando minio ficar pronto..."
    kubectl wait \
        -n "${NAMESPACE}" \
        --for=condition=ready pod \
        --selector=app=minio \
        --timeout=120s

    log_info "  Serviços da aplicação..."
    kubectl apply -f "${ROOT_DIR}/k8s/manifests/services/"

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
        return
    fi

    # Exporta kubeconfig do Kind para o Portainer poder conectar ao K8s
    kind get kubeconfig --name "${CLUSTER_NAME}" > /tmp/arch-analyzer-kubeconfig.yaml
    # Troca localhost pelo IP do nó Kind (acessível dentro da rede Docker)
    KIND_NODE_IP=$(docker inspect "arch-analyzer-control-plane" \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
    sed -i "s/127.0.0.1/${KIND_NODE_IP}/g" /tmp/arch-analyzer-kubeconfig.yaml

    docker run -d \
        --name portainer \
        --restart=unless-stopped \
        -p 9000:9000 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v portainer_data:/data \
        -v /tmp/arch-analyzer-kubeconfig.yaml:/kubeconfig:ro \
        portainer/portainer-ce:latest \
        --admin-password-file /dev/null

    log_success "Portainer iniciado na porta 9000"
    log_info "  Para conectar ao K8s no Portainer:"
    log_info "  Environments → Add Environment → Kubernetes → Agent → Import kubeconfig"
    log_info "  Kubeconfig em: /tmp/arch-analyzer-kubeconfig.yaml (no servidor)"
}

# ─── Aguardar todos os deployments ──────────────────────────────────────────

wait_all_deployments() {
    log_info "Aguardando todos os deployments ficarem prontos (até 5 min)..."

    local deployments=(
        upload-service ai-service report-service frontend
        prometheus grafana loki headlamp
    )

    for dep in "${deployments[@]}"; do
        log_info "  Aguardando ${dep}..."
        kubectl rollout status deployment/"${dep}" \
            -n "${NAMESPACE}" \
            --timeout=300s || log_warning "  ${dep} ainda não pronto (pode ser normal no primeiro boot)"
    done
}

# ─── Status final ────────────────────────────────────────────────────────────

show_status() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                  CLUSTER PRONTO — ACESSO                    ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                              ║"
    echo "║  🌐 Frontend (app principal)  → http://192.168.3.2          ║"
    echo "║  📉 Grafana                   → http://192.168.3.2:3000     ║"
    echo "║     login: fiap / fiap                                      ║"
    echo "║  📈 Prometheus                → http://192.168.3.2:9090     ║"
    echo "║  🐰 RabbitMQ management       → http://192.168.3.2:15672    ║"
    echo "║     login: fiap / fiap                                      ║"
    echo "║  🗄️  MinIO console             → http://192.168.3.2:9002     ║"
    echo "║     login: fiap / fiap1234                                  ║"
    echo "║  🪖 Headlamp (K8s UI)         → http://192.168.3.2:4466     ║"
    echo "║  🐳 Portainer (Docker+K8s UI) → http://192.168.3.2:9000     ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    log_info "Pods no namespace ${NAMESPACE}:"
    kubectl get pods -n "${NAMESPACE}"
    echo ""
    log_info "Para obter token do Headlamp (K8s):"
    echo "  kubectl create token headlamp -n ${NAMESPACE}"
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
    kubectl get pods -n "${NAMESPACE}" 2>/dev/null || echo "Cluster não encontrado."
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
    log_success "Imagens recarregadas!"
}

show_help() {
    echo ""
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos:"
    echo "  start          Sobe o cluster Kind + todos os serviços (padrão)"
    echo "  stop           Destrói o cluster e para o Portainer"
    echo "  status         Mostra status dos pods"
    echo "  logs [serviço] Stream de logs (padrão: frontend)"
    echo "  reload         Reconstrói e recarrega imagens locais no cluster"
    echo "  help           Esta ajuda"
    echo ""
}

main() {
    case "${1:-start}" in
        start)   cmd_start ;;
        stop)    cmd_stop ;;
        status)  cmd_status ;;
        logs)    cmd_logs "$@" ;;
        reload)  cmd_reload_images ;;
        help|--help|-h) show_help ;;
        *) log_error "Comando desconhecido: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
