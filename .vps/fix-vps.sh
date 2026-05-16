#!/bin/bash
################################################################################
# fix-vps.sh — Corrige todos os serviços em VPS já instalada
#
# PROBLEMA RESOLVIDO AQUI:
#   O cluster Kind foi criado sem mapear a porta 30444 (Headlamp).
#   O Kind só mapeia portas no momento de criação — não é possível adicionar
#   depois sem recriar o cluster.
#   SOLUÇÃO: socat faz redirecionamento de porta no host:
#     host:30444 → container kind-control-plane:30444
#   Isso dispensa recriar o cluster e preserva tudo que está rodando.
#
# Uso: sudo ./fix-vps.sh <dominio>
# Ex:  sudo ./fix-vps.sh archanalyzer.brunoretiro.com.br
################################################################################

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

ok()  { echo -e "${GREEN}✓ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}"; }
wrn() { echo -e "${YELLOW}⚠ $1${NC}"; }
inf() { echo -e "${BLUE}ℹ $1${NC}"; }
hdr() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }

[ "$EUID" -ne 0 ] && { err "Execute com sudo: sudo ./fix-vps.sh <dominio>"; exit 1; }

if [ -z "$1" ] || [ "$1" = "example.com" ]; then
    err "Informe o domínio: sudo ./fix-vps.sh archanalyzer.brunoretiro.com.br"
    exit 1
fi

DOMAIN="$1"
PORTAINER_PORT=9000
HEADLAMP_PORT=30444
KIND_HTTP_PORT=30080

if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    err "Certificado SSL não encontrado para $DOMAIN"
    err "Verifique: certbot certificates"
    exit 1
fi

echo ""
echo -e "${BLUE}Domínio: ${YELLOW}$DOMAIN${NC}"
echo ""

###############################################################################
# 1. Portainer
###############################################################################
hdr "1/5 Portainer"

if ! docker ps --format '{{.Names}}' | grep -q "^portainer$"; then
    wrn "Portainer não está rodando — reiniciando..."
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
        sleep 2
        CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
            "http://127.0.0.1:${PORTAINER_PORT}" || echo "000")
        [ "$CODE" != "000" ] && break
    done
fi

P_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    "http://127.0.0.1:${PORTAINER_PORT}" || echo "000")
case "$P_CODE" in
    200|302|307) ok "Portainer rodando — HTTP $P_CODE" ;;
    000) err "Portainer não responde em :${PORTAINER_PORT}" ;;
    *)   wrn "Portainer respondeu HTTP $P_CODE" ;;
esac

###############################################################################
# 2. Headlamp NodePort + socat (contorna limitação do Kind)
###############################################################################
hdr "2/5 Headlamp — NodePort + socat"

# Verificar pod
POD_STATUS=$(kubectl get pods -n headlamp -l app.kubernetes.io/name=headlamp \
    --no-headers 2>/dev/null | awk '{print $3}' | head -1)
[ "$POD_STATUS" = "Running" ] \
    && ok "Pod Headlamp: Running" \
    || { err "Pod Headlamp: ${POD_STATUS:-não encontrado}"; inf "kubectl get pods -n headlamp"; }

# Recriar NodePort dentro do cluster
inf "Recriando Service NodePort no cluster..."
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
ok "Service NodePort criado no cluster"

# Instalar socat se necessário
if ! command -v socat &>/dev/null; then
    inf "Instalando socat..."
    apt-get install -y socat -qq
    ok "socat instalado"
fi

# Parar socat anterior se existir
pkill -f "socat.*30444" 2>/dev/null || true
sleep 1

# Pegar IP do container kind-control-plane
CONTROL_PLANE_IP=$(docker inspect kind-control-plane \
    --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null | head -1)

if [ -z "$CONTROL_PLANE_IP" ]; then
    err "Não foi possível obter IP do kind-control-plane"
    inf "Verifique: docker inspect kind-control-plane"
    exit 1
fi
inf "IP do kind-control-plane: $CONTROL_PLANE_IP"

# Iniciar socat em background com restart automático via systemd
inf "Configurando socat como serviço systemd..."

cat > /etc/systemd/system/headlamp-proxy.service << EOF
[Unit]
Description=Headlamp port proxy (host:30444 → kind-control-plane:30444)
After=docker.service
Wants=docker.service

[Service]
ExecStartPre=/bin/bash -c 'IP=\$(docker inspect kind-control-plane --format "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" 2>/dev/null | head -1); echo \$IP > /tmp/kind-cp-ip'
ExecStart=/bin/bash -c 'IP=\$(cat /tmp/kind-cp-ip); exec socat TCP-LISTEN:30444,fork,reuseaddr TCP:\${IP}:30444'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable headlamp-proxy
systemctl restart headlamp-proxy

inf "Aguardando socat expor porta ${HEADLAMP_PORT}..."
for i in $(seq 1 15); do
    if ss -tlnp 2>/dev/null | grep -q ":${HEADLAMP_PORT}"; then
        ok "Porta ${HEADLAMP_PORT} disponível via socat"
        break
    fi
    sleep 2
done

# Aguardar resposta HTTP
inf "Aguardando resposta HTTP do Headlamp..."
for i in $(seq 1 15); do
    H_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
        "http://127.0.0.1:${HEADLAMP_PORT}" 2>/dev/null || echo "000")
    if [ "$H_CODE" != "000" ]; then
        ok "Headlamp :${HEADLAMP_PORT} → HTTP $H_CODE"
        break
    fi
    sleep 2
done
[ "$H_CODE" = "000" ] && wrn "Headlamp ainda não responde — verifique: systemctl status headlamp-proxy"

###############################################################################
# 3. Nginx — reescrever config via Python
###############################################################################
hdr "3/5 Nginx"

[ -f /etc/nginx/sites-available/default ] && \
    cp /etc/nginx/sites-available/default \
       "/etc/nginx/sites-available/default.bak.$(date +%s)" && \
    inf "Backup criado"

python3 - "$DOMAIN" "$PORTAINER_PORT" "$HEADLAMP_PORT" "$KIND_HTTP_PORT" << 'PYEOF'
import sys

domain    = sys.argv[1]
portainer = sys.argv[2]
headlamp  = sys.argv[3]
kind_port = sys.argv[4]

config = f"""# ── HTTP → HTTPS ──────────────────────────────────────────────────────────────
server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 100M;

    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

# ── HTTPS ─────────────────────────────────────────────────────────────────────
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

    # ── Portainer (/portainer/) ───────────────────────────────────────────────
    # rewrite remove o prefixo /portainer antes de passar ao backend
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

    # ── Headlamp (/k8s/) ─────────────────────────────────────────────────────
    # Sem rewrite — path completo /k8s/ chega ao Headlamp
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

    # ── Apps Kind (/) ─────────────────────────────────────────────────────────
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

with open('/etc/nginx/sites-available/default', 'w') as f:
    f.write(config)
print("Config gerada com sucesso")
PYEOF

if nginx -t 2>&1; then
    systemctl reload nginx
    ok "Nginx recarregado"
else
    err "Nginx com erro — restaurando backup..."
    LAST=$(ls -t /etc/nginx/sites-available/default.bak.* 2>/dev/null | head -1)
    [ -n "$LAST" ] && cp "$LAST" /etc/nginx/sites-available/default \
        && systemctl reload nginx && wrn "Backup restaurado"
    exit 1
fi

###############################################################################
# 4. Permissões e token Headlamp
###############################################################################
hdr "4/5 Permissões e Token Headlamp"

# Recriar ServiceAccount e ClusterRoleBinding do zero (garante permissões limpas)
inf "Recriando ServiceAccount e permissões do headlamp-admin..."
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

# Aguardar SA estar pronto
inf "Aguardando ServiceAccount ficar pronto..."
for i in $(seq 1 10); do
    kubectl get sa headlamp-admin -n headlamp &>/dev/null && break
    sleep 2
done

# Validar permissões
if kubectl auth can-i get pods --all-namespaces     --as=system:serviceaccount:headlamp:headlamp-admin &>/dev/null; then
    ok "Permissões do headlamp-admin validadas (cluster-admin)"
else
    wrn "Permissões podem não estar prontas ainda"
fi

# Gerar token
TOKEN=$(kubectl create token headlamp-admin     -n headlamp --duration=87600h 2>/dev/null || echo "")
if [ -n "$TOKEN" ]; then
    mkdir -p /root/.kube
    echo "$TOKEN" > /root/.kube/headlamp-token
    chmod 600 /root/.kube/headlamp-token
    ok "Token salvo em /root/.kube/headlamp-token"
else
    wrn "Gere manualmente: kubectl create token headlamp-admin -n headlamp --duration=87600h"
fi

###############################################################################
# 5. Testes finais
###############################################################################
hdr "5/5 Testes"

sleep 3

test_url() {
    local label="$1" url="$2"
    shift 2
    local CODE
    CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 "$url" 2>/dev/null || echo "000")
    for e in "$@"; do [ "$CODE" = "$e" ] && { ok "$label → $CODE ✓"; return; }; done
    err "$label → $CODE  (esperado: $*)"
}

test_url "HTTP  localhost"            "http://localhost"                       "301"
test_url "HTTPS localhost"           "https://localhost"                      "200" "301" "404"
test_url "Portainer :9000  (direto)" "http://127.0.0.1:${PORTAINER_PORT}"    "200" "302" "307"
test_url "Headlamp  :30444 (direto)" "http://127.0.0.1:${HEADLAMP_PORT}"     "200" "301" "304" "404"
test_url "https://$DOMAIN"           "https://${DOMAIN}"                     "200" "301" "404" "502"
test_url "/portainer/ via HTTPS"     "https://${DOMAIN}/portainer/"          "200" "302" "307"
test_url "/k8s/       via HTTPS"     "https://${DOMAIN}/k8s/"                "200" "301" "304" "404"

###############################################################################
# Resumo
###############################################################################
echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  URLS DE ACESSO${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "  🐳 Portainer : ${GREEN}https://${DOMAIN}/portainer/${NC}"
echo -e "  ☸️  Headlamp  : ${GREEN}https://${DOMAIN}/k8s/${NC}"
echo -e "  🚀 Apps      : ${GREEN}https://${DOMAIN}/${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Token do Headlamp:${NC}"
cat /root/.kube/headlamp-token 2>/dev/null || \
    echo "  kubectl create token headlamp-admin -n headlamp --duration=87600h"
echo ""
echo -e "${BLUE}Serviço socat (proxy Headlamp):${NC}"
systemctl status headlamp-proxy --no-pager -l | head -8
