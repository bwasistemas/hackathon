#!/bin/bash
# setup-ssl-hmg.sh — Gera o certificado SSL para archanalyzerhmg.brunoretiro.com.br
#
# Uso: sudo bash setup-ssl-hmg.sh <email> [--skip-dns-check] [--force]
#   <email>           Email para notificações Let's Encrypt (obrigatório)
#   --skip-dns-check  Pula verificação de DNS (avança mesmo sem propagação)
#   --force           Renova o certificado mesmo que já exista
#
# Ao final, chama setup-nginx.sh --with-hmg para ativar o bloco HTTPS de HMG.

set -e
source "$(dirname "$0")/lib.sh"
require_root

################################################################################
# Args — $LETSENCRYPT_EMAIL de env var (GitHub Actions) ou CLI
################################################################################

EMAIL="${LETSENCRYPT_EMAIL:-}"
SKIP_DNS=false
FORCE_CERT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-dns-check) SKIP_DNS=true; shift ;;
        --force) FORCE_CERT=true; shift ;;
        -*) shift ;;
        *)  [ -z "$EMAIL" ] && EMAIL="$1"; shift ;;
    esac
done

if [ -z "$EMAIL" ]; then
    err "Email não definido. Use: bash setup-ssl-hmg.sh seu@email.com  ou defina LETSENCRYPT_EMAIL."
fi

CERT_DIR="/etc/letsencrypt/live/${DOMAIN_HMG}"

################################################################################
# Verificar se cert já existe
################################################################################

hdr "SSL — $DOMAIN_HMG"

if [ -d "$CERT_DIR" ] && [ "$FORCE_CERT" = false ]; then
    ok "Certificado já existe: $CERT_DIR"
    inf "Use --force para renovar antecipadamente"
    inf "Ativando bloco HMG no Nginx..."
    bash "$(dirname "$0")/setup-nginx.sh" --with-hmg
    exit 0
fi

################################################################################
# Verificar DNS
################################################################################

if [ "$SKIP_DNS" = false ]; then
    step "Verificando propagação de DNS para $DOMAIN_HMG..."
    DNS_OK=false

    # Tentar até 3x com pausa
    for attempt in 1 2 3; do
        if check_dns "$DOMAIN_HMG"; then
            DNS_OK=true
            break
        fi
        if [ "$attempt" -lt 3 ]; then
            inf "Tentativa $attempt/3 — aguardando 10s..."
            sleep 10
        fi
    done

    if [ "$DNS_OK" = false ]; then
        echo ""
        wrn "DNS ainda não propagou para $DOMAIN_HMG"
        echo -e "${YELLOW}Passos necessários:${NC}"
        echo "  1. No painel DNS do seu domínio, adicione:"
        echo "     Tipo: A  |  Nome: hmg  |  Valor: $(curl -s -4 --max-time 5 ifconfig.me 2>/dev/null)"
        echo "  2. Aguarde propagação (pode levar até 30 minutos)"
        echo "  3. Execute novamente: sudo bash setup-ssl-hmg.sh $EMAIL"
        echo ""
        echo "  Para pular a verificação (se tiver certeza do DNS):"
        echo "  sudo bash setup-ssl-hmg.sh $EMAIL --skip-dns-check"
        exit 1
    fi
fi

################################################################################
# Garantir que Nginx está rodando (para webroot)
################################################################################

if ! service_active nginx; then
    inf "Nginx não está ativo — iniciando..."
    systemctl start nginx
fi

mkdir -p /var/www/certbot

################################################################################
# Gerar certificado
################################################################################

step "Gerando certificado Let's Encrypt para $DOMAIN_HMG..."

CERTBOT_FLAGS=(
    certonly
    -d "$DOMAIN_HMG"
    --email "$EMAIL"
    --agree-tos
    --no-eff-email
    --non-interactive
)
[ "$FORCE_CERT" = true ] && CERTBOT_FLAGS+=(--force-renewal)

# Tentativa 1: webroot (Nginx já está servindo /.well-known)
inf "Tentativa 1/2: webroot..."
if certbot "${CERTBOT_FLAGS[@]}" --webroot -w /var/www/certbot 2>/dev/null; then
    ok "Certificado gerado via webroot"
else
    # Tentativa 2: standalone (para o Nginx temporariamente)
    wrn "Tentativa 2/2: standalone (Nginx parado temporariamente)..."
    systemctl stop nginx
    if certbot "${CERTBOT_FLAGS[@]}" --standalone; then
        ok "Certificado gerado via standalone"
    else
        systemctl start nginx 2>/dev/null || true
        err "Falha ao gerar certificado. Verifique: certbot certificates"
    fi
    systemctl start nginx
fi

################################################################################
# Configurar renovação automática (se ainda não configurado)
################################################################################

RENEW_SCRIPT="/usr/local/bin/renew-certificates.sh"
if [ ! -f "$RENEW_SCRIPT" ]; then
    cat > "$RENEW_SCRIPT" << 'EOF'
#!/bin/bash
LOG=/var/log/certbot-renewal.log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Renovando..." >> "$LOG"
certbot renew --quiet --non-interactive >> "$LOG" 2>&1 \
    && systemctl reload nginx \
    && echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK" >> "$LOG" \
    || echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERRO" >> "$LOG"
EOF
    chmod +x "$RENEW_SCRIPT"
    (crontab -l 2>/dev/null | grep -v renew-certificates
     echo "0 3 * * * $RENEW_SCRIPT") | crontab -
    ok "Renovação automática agendada (3h diariamente)"
fi

################################################################################
# Ativar bloco HMG no Nginx
################################################################################

inf "Ativando bloco HTTPS de HMG no Nginx..."
bash "$(dirname "$0")/setup-nginx.sh" --with-hmg

echo ""
ok "SSL HMG configurado com sucesso!"
inf "Homologação disponível em: https://${DOMAIN_HMG}"
inf "Certificado expira em: $(certbot certificates 2>/dev/null | grep -A3 "$DOMAIN_HMG" | grep Expiry | awk '{print $NF}')"
