#!/bin/bash
################################################################################
# uninstall-vps.sh — Remove TUDO instalado pelo setup-vps.sh
#
# Remove: Kind cluster · Docker containers · Portainer · Headlamp · Helm
#         Nginx config · Certificados Let's Encrypt · socat service
#
# Uso: sudo ./uninstall-vps.sh
################################################################################

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

ok()  { echo -e "${GREEN}✓ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}"; }
wrn() { echo -e "${YELLOW}⚠ $1${NC}"; }
inf() { echo -e "${BLUE}ℹ $1${NC}"; }
hdr() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }

[ "$EUID" -ne 0 ] && { err "Execute com sudo: sudo ./uninstall-vps.sh"; exit 1; }

clear
echo -e "${RED}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║         ⚠  DESINSTALAÇÃO COMPLETA DA VPS  ⚠         ║"
echo "║                                                      ║"
echo "║  Isso irá remover:                                   ║"
echo "║   • Cluster Kind e todos os pods/deployments         ║"
echo "║   • Containers Docker (Portainer)                    ║"
echo "║   • Volumes Docker                                   ║"
echo "║   • Helm e repositórios                              ║"
echo "║   • Configuração do Nginx (restaura padrão)          ║"
echo "║   • Serviço socat (headlamp-proxy)                   ║"
echo "║   • kubectl e Kind binários                          ║"
echo "║                                                      ║"
echo "║  NÃO remove: Docker Engine, Nginx, Certbot, SSL      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

read -rp "Tem certeza? Digite 'sim' para confirmar: " resp
[ "$resp" = "sim" ] || { wrn "Cancelado."; exit 0; }

echo ""
inf "Iniciando desinstalação..."

###############################################################################
# 1. Kind cluster
###############################################################################
hdr "1/8 Removendo cluster Kind"

if command -v kind &>/dev/null; then
    CLUSTERS=$(kind get clusters 2>/dev/null || echo "")
    if [ -n "$CLUSTERS" ]; then
        for cluster in $CLUSTERS; do
            inf "Deletando cluster: $cluster"
            kind delete cluster --name "$cluster" && ok "Cluster '$cluster' removido" || err "Falha ao remover '$cluster'"
        done
    else
        wrn "Nenhum cluster Kind encontrado"
    fi
    rm -f /usr/local/bin/kind
    ok "Binário kind removido"
else
    wrn "Kind não encontrado"
fi

###############################################################################
# 2. kubectl
###############################################################################
hdr "2/8 Removendo kubectl"

if command -v kubectl &>/dev/null; then
    rm -f /usr/local/bin/kubectl
    ok "kubectl removido"
else
    wrn "kubectl não encontrado"
fi

###############################################################################
# 3. Helm
###############################################################################
hdr "3/8 Removendo Helm"

if command -v helm &>/dev/null; then
    rm -f /usr/local/bin/helm
    rm -rf /root/.config/helm
    rm -rf /root/.cache/helm
    rm -rf /root/.local/share/helm
    ok "Helm removido"
else
    wrn "Helm não encontrado"
fi

###############################################################################
# 4. Docker containers e volumes
###############################################################################
hdr "4/8 Removendo containers e volumes Docker"

if command -v docker &>/dev/null; then
    # Parar e remover todos os containers relacionados
    for name in portainer; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
            docker stop "$name" 2>/dev/null && docker rm "$name" 2>/dev/null
            ok "Container '$name' removido"
        else
            wrn "Container '$name' não encontrado"
        fi
    done

    # Remover volumes criados pelo setup
    for vol in portainer_data; do
        if docker volume ls -q | grep -q "^${vol}$"; then
            docker volume rm "$vol" 2>/dev/null
            ok "Volume '$vol' removido"
        else
            wrn "Volume '$vol' não encontrado"
        fi
    done

    # Remover imagens do Portainer (opcional — economiza espaço)
    docker rmi portainer/portainer-ce:latest 2>/dev/null && \
        ok "Imagem Portainer removida" || wrn "Imagem Portainer não encontrada"

    # Limpar containers/networks/volumes órfãos do Kind
    docker network rm kind 2>/dev/null && ok "Network 'kind' removida" || true
else
    wrn "Docker não encontrado"
fi

###############################################################################
# 5. Serviço socat (headlamp-proxy)
###############################################################################
hdr "5/8 Removendo serviço socat"

if systemctl list-units --all | grep -q "headlamp-proxy"; then
    systemctl stop headlamp-proxy 2>/dev/null
    systemctl disable headlamp-proxy 2>/dev/null
    rm -f /etc/systemd/system/headlamp-proxy.service
    systemctl daemon-reload
    ok "Serviço headlamp-proxy removido"
else
    wrn "Serviço headlamp-proxy não encontrado"
fi

pkill -f "socat.*30444" 2>/dev/null && ok "Processo socat encerrado" || true

###############################################################################
# 6. Nginx — restaurar configuração padrão
###############################################################################
hdr "6/8 Restaurando configuração do Nginx"

if command -v nginx &>/dev/null; then
    # Remover backups antigos
    rm -f /etc/nginx/sites-available/default.bak.* 2>/dev/null
    rm -f /etc/nginx/sites-available/default.backup 2>/dev/null

    # Restaurar config padrão simples
    cat > /etc/nginx/sites-available/default << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /var/www/html;
    index index.html index.htm index.nginx-debian.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
EOF

    nginx -t && systemctl reload nginx
    ok "Nginx restaurado para configuração padrão"
else
    wrn "Nginx não encontrado"
fi

###############################################################################
# 7. Arquivos e configs do setup
###############################################################################
hdr "7/8 Removendo arquivos do setup"

rm -f /usr/local/bin/renew-certificates.sh && ok "Script de renovação removido" || true
rm -f /root/.kube/headlamp-token && ok "Token Headlamp removido" || true
rm -f /tmp/kind-config.yaml && ok "Config Kind removida" || true
rm -f /tmp/kind-cp-ip && true

# Remover cron de renovação de certificados
crontab -l 2>/dev/null | grep -v renew-certificates | crontab - && \
    ok "Cron de renovação removido" || true

# Limpar kubeconfig do Kind
if [ -f /root/.kube/config ]; then
    rm -f /root/.kube/config
    ok "kubeconfig removido"
fi

###############################################################################
# 8. Verificação final
###############################################################################
hdr "8/8 Verificação final"

echo -e "${BLUE}Processos na porta 30080/30444:${NC}"
ss -tlnp | grep -E ":30080|:30444" || ok "Portas 30080/30444 livres"

echo -e "\n${BLUE}Containers Docker restantes:${NC}"
docker ps -a 2>/dev/null || true

echo -e "\n${BLUE}Volumes Docker restantes:${NC}"
docker volume ls 2>/dev/null || true

echo -e "\n${BLUE}Binários removidos:${NC}"
for bin in kind kubectl helm; do
    command -v $bin &>/dev/null \
        && err "$bin ainda presente: $(which $bin)" \
        || ok "$bin removido"
done

echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Desinstalação concluída!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Agora você pode rodar o setup novamente:${NC}"
echo "  sudo ./setup-vps.sh archanalyzer.brunoretiro.com.br seu@email.com"
echo ""
echo -e "${BLUE}Nota: Docker Engine, Nginx e certificados SSL foram mantidos.${NC}"
echo -e "${BLUE}Para remover o Docker também: apt-get remove -y docker-ce docker-ce-cli containerd.io${NC}"
echo ""
