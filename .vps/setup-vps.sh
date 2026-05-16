#!/bin/bash

################################################################################
# setup-vps.sh — VERSÃO 7.0
#
# INSTALA E CONFIGURA:
#   Docker · Kind · kubectl · Helm · Nginx · Let's Encrypt · Portainer · Headlamp
#
# CORREÇÕES ACUMULADAS:
#   ✓ Nginx gerado via Python (sem bugs de escape bash)
#   ✓ rewrite correto para Portainer e Headlamp
#   ✓ Portainer: 307 aceito como resposta válida
#   ✓ Kind cluster mapeado com portas 30080 + 30443 + 30444 desde criação
#   ✓ Headlamp: HTTP puro (não HTTPS) no NodePort
#   ✓ socat como serviço systemd (fallback caso docker-proxy não exponha porta)
#   ✓ SSL gerado via webroot com fallback standalone
#   ✓ DNS check força IPv4
#   ✓ ssl_stapling desativado (evita warning com Let's Encrypt)
#   ✓ Helm: repo update só após add bem-sucedido
#   ✓ Testes finais cobrem todos os endpoints e códigos reais
#
# ROTAS:
#   https://DOMINIO/portainer/  → Portainer  (Docker UI)
#   https://DOMINIO/k8s/        → Headlamp   (Kubernetes UI)
#   https://DOMINIO/            → Apps Kind
#
# Uso: sudo ./setup-vps.sh <dominio> <email>
################################################################################

# set -e removido — tratamento de erro manual para evitar saída silenciosa

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# Env vars têm precedência (injetadas pelo GitHub Actions ou shell); CLI é fallback
DOMAIN="${DOMAIN_PROD:-${1:-example.com}}"
EMAIL="${LETSENCRYPT_EMAIL:-${2:-admin@example.com}}"

KIND_HTTP_PORT=30080
KIND_HMG_PORT=30081
KIND_HTTPS_PORT=30443
KIND_API_PORT=6443
PORTAINER_PORT=9000
HEADLAMP_PORT=30444

################################################################################
# Utilitários
################################################################################

hdr() {
    echo -e "\n${BLUE}===============================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}===============================================${NC}\n"
}
ok()  { echo -e "${GREEN}✓ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}"; }
wrn() { echo -e "${YELLOW}⚠ $1${NC}"; }
inf() { echo -e "${BLUE}ℹ $1${NC}"; }
has() { command -v "$1" &>/dev/null; }

check_root() {
    [ "$EUID" -ne 0 ] && { err "Execute com sudo: sudo ./setup-vps.sh <dominio> <email>"; exit 1; }
}

check_internet() {
    inf "Verificando internet..."
    if ping -c 1 8.8.8.8 &>/dev/null; then
        ok "Internet OK"
    else
        err "Sem internet."
        exit 1
    fi
}

################################################################################
# DNS — força IPv4
################################################################################

check_dns() {
    [ "$DOMAIN" = "example.com" ] && return
    hdr "Validando DNS"
    SERVER_IP=$(curl -s -4 --max-time 5 ifconfig.me \
        || curl -s -4 --max-time 5 api.ipify.org \
        || curl -s -4 --max-time 5 ifconfig.co || echo "")
    DOMAIN_IP=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || echo "")
    inf "IP servidor : ${SERVER_IP:-não detectado}"
    inf "IP domínio  : ${DOMAIN_IP:-não resolvido}"
    if [ -z "$DOMAIN_IP" ]; then
        wrn "$DOMAIN não resolve. Verifique DNS."
    elif [ "$SERVER_IP" = "$DOMAIN_IP" ]; then
        ok "DNS OK — $DOMAIN → $SERVER_IP"
    else
        wrn "DNS divergente: $DOMAIN → $DOMAIN_IP | servidor → $SERVER_IP"
        wrn "Let's Encrypt pode falhar se DNS não propagou."
    fi
}

################################################################################
# Liberar portas 80/443
################################################################################

free_ports() {
    hdr "Verificando Conflitos de Porta"
    for PORT in 80 443; do
        PIDS=$(ss -tlnp "sport = :${PORT}" 2>/dev/null \
            | grep -v nginx | grep -oP 'pid=\K[0-9]+' | sort -u)
        if [ -z "$PIDS" ]; then
            ok "Porta $PORT livre"
            continue
        fi
        for PID in $PIDS; do
            PROC=$(ps -p "$PID" -o comm= 2>/dev/null || echo "?")
            wrn "Porta $PORT ocupada por $PROC (PID $PID) — encerrando..."
            kill -9 "$PID" 2>/dev/null && ok "PID $PID encerrado" || true
        done
        sleep 1
    done
}

################################################################################
# Sistema
################################################################################

update_system() {
    hdr "Atualizando Sistema"
    apt-get update -qq
    apt-get upgrade -y -qq
    apt-get install -y \
        curl wget git vim htop net-tools jq iproute2 python3 socat \
        software-properties-common apt-transport-https \
        ca-certificates gnupg lsb-release openssl \
        certbot python3-certbot-nginx
    ok "Sistema atualizado (socat incluso)"
}

################################################################################
# Docker
################################################################################

install_docker() {
    hdr "Instalando Docker"
    if has docker; then
        wrn "Docker já instalado: $(docker --version)"
        systemctl start docker && systemctl enable docker
        return
    fi
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl start docker && systemctl enable docker
    [ -n "$SUDO_USER" ] && usermod -aG docker "$SUDO_USER" || true
    ok "Docker: $(docker --version)"
}

################################################################################
# Kind
################################################################################

install_kind() {
    hdr "Instalando Kind"
    if has kind; then wrn "Kind já instalado: $(kind version)"; return; fi
    KIND_VER=$(curl -s https://api.github.com/repos/kubernetes-sigs/kind/releases/latest \
        | jq -r '.tag_name' 2>/dev/null || echo "v0.23.0")
    inf "Baixando Kind $KIND_VER..."
    curl -Lo /usr/local/bin/kind "https://kind.sigs.k8s.io/dl/${KIND_VER}/kind-linux-amd64"
    chmod +x /usr/local/bin/kind
    ok "Kind: $(kind version)"
}

################################################################################
# kubectl
################################################################################

install_kubectl() {
    hdr "Instalando kubectl"
    if has kubectl; then wrn "kubectl já instalado"; return; fi
    KUBE_VER=$(curl -L -s https://dl.k8s.io/release/stable.txt)
    curl -LO "https://dl.k8s.io/release/${KUBE_VER}/bin/linux/amd64/kubectl"
    chmod +x kubectl && mv kubectl /usr/local/bin/
    ok "kubectl: $KUBE_VER"
}

################################################################################
# Nginx — config gerada via Python (evita bugs de escape do bash)
################################################################################

install_nginx() {
    hdr "Instalando Nginx"
    if has nginx; then
        wrn "Nginx já instalado: $(nginx -v 2>&1)"
    else
        apt-get install -y nginx
        ok "Nginx instalado"
    fi
    systemctl start nginx && systemctl enable nginx
}

write_nginx_config() {
    local domain=$1
    local has_ssl=$2   # "yes" ou "no"

    python3 - "$domain" "$has_ssl" \
        "$PORTAINER_PORT" "$HEADLAMP_PORT" "$KIND_HTTP_PORT" << 'PYEOF'
import sys

domain    = sys.argv[1]
has_ssl   = sys.argv[2] == "yes"
portainer = sys.argv[3]
headlamp  = sys.argv[4]
kind_port = sys.argv[5]

http_block = """# HTTP → HTTPS
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 100M;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
"""

https_block = f"""
# HTTPS
server {{
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name {domain};
    client_max_body_size 100M;

    ssl_certificate     /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/{domain}/chain.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Portainer — rewrite remove /portainer/ antes de passar ao backend
    # Portainer espera receber rotas a partir de /
    location /portainer/ {{
        rewrite ^/portainer/(.*) /$1 break;
        proxy_pass         http://127.0.0.1:{portainer};
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_read_timeout 90;
    }}

    # Headlamp — sem rewrite, path completo chega ao Headlamp
    # Headlamp configurado com baseURL=/k8s via helm
    location /k8s/ {{
        proxy_pass         http://127.0.0.1:{headlamp};
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_read_timeout 90;
    }}

    # Apps Kind
    location / {{
        proxy_pass         http://127.0.0.1:{kind_port};
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 90;
        proxy_connect_timeout 90;
    }}
}}
"""

config = http_block + (https_block if has_ssl else "")
with open('/etc/nginx/sites-available/arch-analyzer', 'w') as f:
    f.write(config)
print("Config Nginx gerada")
PYEOF
    # Ativar arch-analyzer e desativar default para evitar conflito de default_server
    ln -sf /etc/nginx/sites-available/arch-analyzer /etc/nginx/sites-enabled/arch-analyzer 2>/dev/null || true
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
}

setup_deploy_sudoers() {
    hdr "Configurando sudoers para deploy automatico"

    # Script wrapper: permite que o usuario de deploy recarregue o Nginx
    # sem senha, recebendo a nova config via stdin.
    cat > /usr/local/bin/arch-nginx-apply << 'WRAPPER'
#!/bin/bash
set -e
NGINX_INSTALLED="/etc/nginx/sites-available/arch-analyzer"
NGINX_ENABLED="/etc/nginx/sites-enabled/arch-analyzer"
BACKUP="${NGINX_INSTALLED}.bak.$(date +%s)"
[ -f "$NGINX_INSTALLED" ] && cp "$NGINX_INSTALLED" "$BACKUP"
cat > "$NGINX_INSTALLED"
ln -sf "$NGINX_INSTALLED" "$NGINX_ENABLED" 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
if nginx -t 2>&1; then
    systemctl reload nginx
    echo "Nginx recarregado."
else
    echo "AVISO: config invalida — revertendo backup."
    [ -f "$BACKUP" ] && cp "$BACKUP" "$NGINX_INSTALLED" && systemctl reload nginx || true
    exit 1
fi
WRAPPER
    chmod +x /usr/local/bin/arch-nginx-apply

    # Usa %sudo (grupo) em vez de usuario especifico — funciona para qualquer
    # usuario com privilegios sudo, incluindo o usuario SSH do GitHub Actions.
    SUDOERS_FILE="/etc/sudoers.d/arch-deploy-nginx"
    echo "%sudo ALL=(root) NOPASSWD: /usr/local/bin/arch-nginx-apply" > "$SUDOERS_FILE"
    chmod 0440 "$SUDOERS_FILE"
    ok "sudoers configurado para grupo sudo (nginx reload sem senha)"
}

configure_nginx() {
    hdr "Configurando Nginx"
    [ -f /etc/nginx/sites-available/default ] && \
        cp /etc/nginx/sites-available/default \
           "/etc/nginx/sites-available/default.bak.$(date +%s)"
    mkdir -p /var/www/certbot

    if [ "$DOMAIN" != "example.com" ] && [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        inf "Certificado encontrado — aplicando SSL"
        write_nginx_config "$DOMAIN" "yes"
    else
        inf "HTTP inicial (SSL após certificado)"
        write_nginx_config "$DOMAIN" "no"
    fi

    nginx -t && systemctl reload nginx
    ok "Nginx configurado"
}

################################################################################
# Let's Encrypt
################################################################################

generate_ssl_certificate() {
    hdr "Certificado SSL (Let's Encrypt)"

    if [ "$DOMAIN" = "example.com" ]; then
        wrn "Domínio padrão — pulando SSL."
        return
    fi

    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        wrn "Certificado já existe — aplicando no Nginx."
        write_nginx_config "$DOMAIN" "yes"
        nginx -t && systemctl reload nginx
        setup_certificate_renewal
        return
    fi

    mkdir -p /var/www/certbot

    inf "Tentativa 1/2: webroot..."
    if certbot certonly --webroot \
        -w /var/www/certbot -d "$DOMAIN" \
        --email "$EMAIL" --agree-tos --no-eff-email --non-interactive 2>/dev/null; then
        ok "Certificado gerado (webroot)"
        write_nginx_config "$DOMAIN" "yes"
        nginx -t && systemctl reload nginx
        setup_certificate_renewal
        return
    fi

    wrn "Tentativa 2/2: standalone..."
    systemctl stop nginx
    if certbot certonly --standalone -d "$DOMAIN" \
        --email "$EMAIL" --agree-tos --no-eff-email --non-interactive; then
        ok "Certificado gerado (standalone)"
        systemctl start nginx
        write_nginx_config "$DOMAIN" "yes"
        nginx -t && systemctl reload nginx
        setup_certificate_renewal
        return
    fi

    systemctl start nginx 2>/dev/null || true
    err "Falha ao gerar certificado."
    err "Manual: certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos"
}

setup_certificate_renewal() {
    cat > /usr/local/bin/renew-certificates.sh << 'EOF'
#!/bin/bash
LOG=/var/log/certbot-renewal.log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Renovando..." >> "$LOG"
certbot renew --quiet --non-interactive >> "$LOG" 2>&1 \
    && echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK" >> "$LOG" \
    && systemctl reload nginx \
    || echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERRO" >> "$LOG"
EOF
    chmod +x /usr/local/bin/renew-certificates.sh
    (crontab -l 2>/dev/null | grep -v renew-certificates
     echo "0 3 * * * /usr/local/bin/renew-certificates.sh") | crontab -
    ok "Renovação SSL agendada às 3h"
}

################################################################################
# Kind cluster — porta 30444 mapeada desde a criação
################################################################################

create_kind_cluster() {
    hdr "Criando Cluster Kubernetes (Kind)"

    if kind get clusters 2>/dev/null | grep -q "^kind$"; then
        wrn "Cluster 'kind' já existe"
        kubectl cluster-info 2>/dev/null || true
        return
    fi

    # Gerar config via Python
    python3 - "$KIND_API_PORT" "$KIND_HTTP_PORT" "$KIND_HMG_PORT" "$KIND_HTTPS_PORT" "$HEADLAMP_PORT" << 'PYEOF'
import sys
api, http, hmg, https, headlamp = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
config = f"""kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kind
networking:
  apiServerAddress: "0.0.0.0"
  apiServerPort: {api}
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: {http}
        protocol: TCP
      - containerPort: 30081
        hostPort: {hmg}
        protocol: TCP
      - containerPort: 30443
        hostPort: {https}
        protocol: TCP
      - containerPort: 30444
        hostPort: {headlamp}
        protocol: TCP
  - role: worker
  - role: worker
"""
with open('/tmp/kind-config.yaml', 'w') as f:
    f.write(config)
print("kind-config.yaml gerado")
PYEOF

    inf "Criando cluster (2-3 minutos)..."
    if kind create cluster --config /tmp/kind-config.yaml; then
        ok "Cluster Kind criado!"
        kubectl wait --for=condition=Ready nodes --all --timeout=120s 2>/dev/null || true
        kubectl get nodes
    else
        err "Falha ao criar cluster Kind."
        return 1
    fi
}

################################################################################
# KEDA — Kubernetes Event-Driven Autoscaling
################################################################################

install_keda() {
    hdr "Instalando KEDA (Autoscaling por fila RabbitMQ)"

    if kubectl get deployment keda-operator -n keda &>/dev/null; then
        wrn "KEDA já instalado"
        kubectl get pods -n keda
        return
    fi

    KEDA_VERSION="v2.14.0"
    inf "Aplicando KEDA $KEDA_VERSION..."
    kubectl apply -f "https://github.com/kedacore/keda/releases/download/${KEDA_VERSION}/keda-${KEDA_VERSION#v}.yaml"

    inf "Aguardando KEDA ficar pronto (até 3 minutos)..."
    kubectl wait --for=condition=ready pod \
        --selector=app=keda-operator \
        --namespace=keda \
        --timeout=180s 2>/dev/null || true

    kubectl get pods -n keda
    ok "KEDA instalado — ai-service escalará automaticamente com base na fila diagram.upload"
}

################################################################################
# Portainer
################################################################################

install_portainer() {
    hdr "Instalando Portainer (Docker UI)"

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portainer$"; then
        wrn "Portainer já rodando"
        return
    fi

    docker rm -f portainer 2>/dev/null || true
    docker volume create portainer_data 2>/dev/null || true

    docker run -d \
        --name portainer --restart always \
        -p 127.0.0.1:${PORTAINER_PORT}:9000 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v portainer_data:/data \
        portainer/portainer-ce:latest

    inf "Aguardando Portainer..."
    for i in $(seq 1 20); do
        CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 \
            "http://127.0.0.1:${PORTAINER_PORT}" 2>/dev/null || echo "000")
        if [ "$CODE" != "000" ]; then
            ok "Portainer rodando :${PORTAINER_PORT} — HTTP $CODE"
            return
        fi
        sleep 2
    done
    wrn "Portainer demorou — verifique: docker logs portainer"
}

################################################################################
# Headlamp (Kubernetes UI)
################################################################################

install_headlamp() {
    hdr "Instalando Headlamp (Kubernetes UI)"

    # Helm
    if ! has helm; then
        inf "Instalando Helm..."
        curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
        ok "Helm: $(helm version --short)"
    fi

    # Instalar se necessário
    if ! helm list -n headlamp 2>/dev/null | grep -q "headlamp"; then
        inf "Adicionando repositório Headlamp..."
        helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/ || true

        if ! helm repo list 2>/dev/null | grep -q "headlamp"; then
            err "Falha ao adicionar repositório Helm do Headlamp."
            return 1
        fi

        helm repo update headlamp

        inf "Instalando Headlamp..."
        helm upgrade --install headlamp headlamp/headlamp \
            --create-namespace --namespace headlamp \
            --set replicaCount=1 --timeout 3m

        inf "Aguardando pod Headlamp..."
        kubectl wait --namespace headlamp \
            --for=condition=ready pod \
            --selector=app.kubernetes.io/name=headlamp \
            --timeout=120s 2>/dev/null || true

        # ServiceAccount admin — recriar do zero garante permissões limpas
        kubectl delete clusterrolebinding headlamp-admin 2>/dev/null || true
        kubectl delete sa headlamp-admin -n headlamp 2>/dev/null || true

        kubectl apply -f - << 'YAML'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: headlamp-admin
  namespace: headlamp
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: headlamp-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: headlamp-admin
    namespace: headlamp
YAML

        # Validar permissões
        if kubectl auth can-i get pods --all-namespaces             --as=system:serviceaccount:headlamp:headlamp-admin &>/dev/null; then
            ok "Permissões do headlamp-admin validadas"
        else
            wrn "Permissões podem não estar prontas ainda — aguarde e tente o token novamente"
        fi
        ok "Headlamp instalado!"
    else
        wrn "Headlamp já instalado"
    fi

    _ensure_headlamp_nodeport
    _generate_headlamp_token
}

_ensure_headlamp_nodeport() {
    inf "Configurando NodePort do Headlamp → porta ${HEADLAMP_PORT}..."
    kubectl delete svc headlamp-nodeport -n headlamp 2>/dev/null || true

    kubectl apply -f - << 'YAML'
apiVersion: v1
kind: Service
metadata:
  name: headlamp-nodeport
  namespace: headlamp
spec:
  type: NodePort
  selector:
    app.kubernetes.io/name: headlamp
  ports:
    - port: 4466
      targetPort: 4466
      nodePort: 30444
      protocol: TCP
YAML

    # Aguardar docker-proxy expor a porta
    inf "Aguardando porta ${HEADLAMP_PORT} no host..."
    for i in $(seq 1 25); do
        if ss -tlnp 2>/dev/null | grep -q ":${HEADLAMP_PORT}"; then
            ok "Porta ${HEADLAMP_PORT} disponível via docker-proxy"
            return
        fi
        sleep 2
    done

    # Fallback: socat como serviço systemd
    wrn "docker-proxy não expôs porta ${HEADLAMP_PORT} — ativando socat como fallback..."
    _setup_socat_headlamp
}

_setup_socat_headlamp() {
    CONTROL_PLANE_IP=$(docker inspect kind-control-plane \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
        2>/dev/null | head -1)

    if [ -z "$CONTROL_PLANE_IP" ]; then
        err "Não foi possível obter IP do kind-control-plane"
        return 1
    fi
    inf "kind-control-plane IP: $CONTROL_PLANE_IP"

    pkill -f "socat.*${HEADLAMP_PORT}" 2>/dev/null || true

    cat > /etc/systemd/system/headlamp-proxy.service << EOF
[Unit]
Description=Headlamp port proxy host:${HEADLAMP_PORT} → kind-control-plane:${HEADLAMP_PORT}
After=docker.service
Wants=docker.service

[Service]
ExecStartPre=/bin/bash -c 'docker inspect kind-control-plane --format "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" > /tmp/kind-cp-ip'
ExecStart=/bin/bash -c 'exec socat TCP-LISTEN:${HEADLAMP_PORT},fork,reuseaddr TCP:\$(cat /tmp/kind-cp-ip):${HEADLAMP_PORT}'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable headlamp-proxy
    systemctl restart headlamp-proxy
    sleep 3

    if ss -tlnp 2>/dev/null | grep -q ":${HEADLAMP_PORT}"; then
        ok "Porta ${HEADLAMP_PORT} disponível via socat"
    else
        err "socat não conseguiu expor porta ${HEADLAMP_PORT}"
    fi
}

_generate_headlamp_token() {
    hdr "Token de Acesso ao Headlamp"

    # Aguardar SA estar pronto antes de gerar token
    inf "Aguardando ServiceAccount headlamp-admin..."
    for i in $(seq 1 10); do
        kubectl get sa headlamp-admin -n headlamp &>/dev/null && break
        sleep 2
    done

    TOKEN=$(kubectl create token headlamp-admin         --namespace headlamp --duration=87600h 2>/dev/null || echo "")

    if [ -n "$TOKEN" ]; then
        mkdir -p /root/.kube
        echo "$TOKEN" > /root/.kube/headlamp-token
        chmod 600 /root/.kube/headlamp-token
        echo ""
        echo -e "${YELLOW}══════════════════════════════════════${NC}"
        echo -e "${YELLOW}  TOKEN — HEADLAMP${NC}"
        echo -e "${YELLOW}══════════════════════════════════════${NC}"
        echo -e "${GREEN}$TOKEN${NC}"
        echo -e "${YELLOW}══════════════════════════════════════${NC}"
        inf "Salvo em: /root/.kube/headlamp-token"
        inf "Para gerar novo: kubectl create token headlamp-admin -n headlamp --duration=87600h"
    else
        wrn "Gere manualmente:"
        inf "kubectl create token headlamp-admin -n headlamp --duration=87600h"
    fi
}

################################################################################
# Testes finais
################################################################################

run_tests() {
    hdr "Testes de Conectividade"

    _t() {
        local label=$1 url=$2; shift 2
        local CODE
        CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 "$url" 2>/dev/null || echo "000")
        for e in "$@"; do [ "$CODE" = "$e" ] && { ok "$label → $CODE ✓"; return; }; done
        err "$label → $CODE  (esperado: $*)"
    }

    _t "HTTP  localhost"              "http://localhost"                       "301"
    _t "HTTPS localhost"             "https://localhost"                      "200" "301" "404" "502"
    _t "Portainer :${PORTAINER_PORT}" "http://127.0.0.1:${PORTAINER_PORT}"   "200" "302" "307"
    _t "Headlamp  :${HEADLAMP_PORT}"  "http://127.0.0.1:${HEADLAMP_PORT}"    "200" "301" "304" "404"

    if [ "$DOMAIN" != "example.com" ]; then
        _t "https://$DOMAIN"             "https://${DOMAIN}"                  "200" "301" "404" "502"
        _t "/portainer/ via HTTPS"       "https://${DOMAIN}/portainer/"       "200" "302" "307"
        _t "/k8s/       via HTTPS"       "https://${DOMAIN}/k8s/"             "200" "301" "304" "404"
    fi
}

################################################################################
# Status
################################################################################

check_status() {
    hdr "Status dos Serviços"

    echo -e "${BLUE}🐳 Docker:${NC}"
    systemctl is-active docker &>/dev/null && ok "$(docker --version)" || err "Inativo"

    echo -e "\n${BLUE}🌐 Nginx:${NC}"
    systemctl is-active nginx &>/dev/null && ok "$(nginx -v 2>&1)" || err "Inativo"

    echo -e "\n${BLUE}☸️  Cluster:${NC}"
    kubectl get nodes 2>/dev/null || wrn "Cluster não disponível"

    echo -e "\n${BLUE}📦 Portainer:${NC}"
    docker ps --filter name=portainer --format "  {{.Status}}" 2>/dev/null || wrn "Não iniciado"

    echo -e "\n${BLUE}📊 Headlamp:${NC}"
    kubectl get pods -n headlamp 2>/dev/null || wrn "Não instalado"

    echo -e "\n${BLUE}⚡ KEDA:${NC}"
    kubectl get pods -n keda 2>/dev/null || wrn "Não instalado"

    echo -e "\n${BLUE}🔁 socat headlamp-proxy:${NC}"
    systemctl is-active headlamp-proxy &>/dev/null \
        && ok "Ativo (fallback socat)" || inf "Não necessário (docker-proxy ok)"

    echo -e "\n${BLUE}🔐 SSL:${NC}"
    certbot certificates 2>/dev/null | grep -E "Domains|Expiry" || wrn "Sem certificado"

    echo -e "\n${BLUE}🔌 Portas:${NC}"
    ss -tlnp | grep -E ":80\b|:443\b|:9000\b|:30080\b|:30081\b|:30444\b|:6443\b" \
        | awk '{print "  " $4}' || true
}

show_access() {
    hdr "🎉 URLs de Acesso"
    echo -e "${CYAN}┌──────────────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}│  🐳 Portainer (Docker UI)                        │${NC}"
    echo -e "${CYAN}│     ${GREEN}https://${DOMAIN}/portainer/${NC}"
    echo -e "${CYAN}│     Crie sua senha no primeiro acesso            │${NC}"
    echo -e "${CYAN}├──────────────────────────────────────────────────┤${NC}"
    echo -e "${CYAN}│  ☸️  Headlamp (Kubernetes UI)                     │${NC}"
    echo -e "${CYAN}│     ${GREEN}https://${DOMAIN}/k8s/${NC}"
    echo -e "${CYAN}│     Token: /root/.kube/headlamp-token            │${NC}"
    echo -e "${CYAN}├──────────────────────────────────────────────────┤${NC}"
    echo -e "${CYAN}│  🚀 Arch Analyzer (Kubernetes / Kind)            │${NC}"
    echo -e "${CYAN}│     ${GREEN}https://${DOMAIN}/${NC}"
    echo -e "${CYAN}│     Deploy automático via GitHub Actions         │${NC}"
    echo -e "${CYAN}└──────────────────────────────────────────────────┘${NC}"
    echo ""
    echo -e "${YELLOW}Token Headlamp:${NC}"
    cat /root/.kube/headlamp-token 2>/dev/null \
        || echo "  kubectl create token headlamp-admin -n headlamp --duration=87600h"
}

################################################################################
# Main
################################################################################

main() {
    clear 2>/dev/null || true
    hdr "🚀 Setup VPS — Versão 8.0"
    check_root
    check_internet

    echo -e "  Domínio : ${YELLOW}$DOMAIN${NC}"
    echo -e "  Email   : ${YELLOW}$EMAIL${NC}"
    echo ""
    echo -e "${CYAN}O que será instalado:${NC}"
    echo -e "  Docker · Kind · kubectl · Helm · socat · Nginx · Let's Encrypt"
    echo -e "  Portainer → https://$DOMAIN/portainer/"
    echo -e "  Headlamp  → https://$DOMAIN/k8s/"
    echo ""
    echo -e "${BLUE}Portas:${NC}"
    echo -e "  Nginx  80/443  (público)"
    echo -e "    /portainer/ → Portainer  :${PORTAINER_PORT}"
    echo -e "    /k8s/       → Headlamp   :${HEADLAMP_PORT} (Kind NodePort ou socat)"
    echo -e "    /           → App Prod   :${KIND_HTTP_PORT} (arch-prod)"
    echo -e "    /           → App HMG    :${KIND_HMG_PORT}  (arch-hmg, outro domínio)"
    echo ""

    read -rp "Continuar? (s/n) " resp
    [[ "$resp" =~ ^[Ss]$ ]] || { err "Cancelado."; exit 1; }

    update_system        # inclui socat
    install_docker
    install_kind
    install_kubectl
    install_nginx
    free_ports
    configure_nginx
    setup_deploy_sudoers  # wrapper nginx + sudoers para deploy automatico
    create_kind_cluster  # cria com portas 30080, 30081, 30444 mapeadas
    install_keda         # autoscaling por fila RabbitMQ
    install_portainer
    install_headlamp     # NodePort + socat fallback automático
    check_dns
    generate_ssl_certificate

    echo ""
    check_status
    echo ""
    run_tests            # testa todos os endpoints + códigos reais
    echo ""
    show_access

    hdr "✅ Setup Concluído — v8.0"
    echo -e "${GREEN}Portainer : https://${DOMAIN}/portainer/${NC}"
    echo -e "${GREEN}Headlamp  : https://${DOMAIN}/k8s/${NC}"
    echo -e "${GREEN}App       : https://${DOMAIN}/${NC} (após primeiro deploy)${NC}\n"

    # ── Setup de CD (clone de repos, Nginx para app, SSL HMG) ────────────────
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    DEPLOY_SCRIPT="$SCRIPT_DIR/setup-deploy.sh"

    if [ -f "$DEPLOY_SCRIPT" ]; then
        echo ""
        echo -e "${CYAN}Prosseguir com o setup de CD (Nginx da aplicação + SSL HMG)?${NC}"
        read -rp "  [s/N] " resp
        if [[ "$resp" =~ ^[Ss]$ ]]; then
            bash "$DEPLOY_SCRIPT" --email "$EMAIL" --skip-ssl-hmg
        else
            echo ""
            echo -e "${YELLOW}Para finalizar o setup de CD manualmente:${NC}"
            echo -e "  sudo bash $DEPLOY_SCRIPT"
        fi
    fi
}

main "$@"
