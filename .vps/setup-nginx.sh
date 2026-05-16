#!/bin/bash
# setup-nginx.sh — Aplica o config Nginx para o Arch Analyzer
#
# Uso: sudo bash setup-nginx.sh [--with-hmg]
#   --with-hmg  Inclui o bloco HTTPS de homologação (requer cert existente)
#
# Sem --with-hmg: aplica apenas o bloco de produção.
# O setup-ssl-hmg.sh chama este script com --with-hmg após gerar o cert.

set -e
source "$(dirname "$0")/lib.sh"
require_root

WITH_HMG=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-hmg) WITH_HMG=true; shift ;;
        *) shift ;;
    esac
done

################################################################################
# Verificações
################################################################################

hdr "Configurando Nginx"

require_cmd nginx
require_cmd python3

[ -f "$NGINX_CONF_SRC" ] || err "Config não encontrado: $NGINX_CONF_SRC"

################################################################################
# Backup do config atual
################################################################################

if [ -f "$NGINX_CONF_DEST" ]; then
    BACKUP="${NGINX_CONF_DEST}.bak.$(date +%s)"
    cp "$NGINX_CONF_DEST" "$BACKUP"
    inf "Backup salvo: $BACKUP"
fi

################################################################################
# Gerar config final (com ou sem bloco HMG)
################################################################################

if [ "$WITH_HMG" = true ]; then
    # Verificar se o certificado HMG existe
    HMG_CERT="/etc/letsencrypt/live/${DOMAIN_HMG}/fullchain.pem"
    if [ ! -f "$HMG_CERT" ]; then
        wrn "Certificado HMG não encontrado: $HMG_CERT"
        wrn "Execute setup-ssl-hmg.sh primeiro, ou use sem --with-hmg"
        exit 1
    fi
    step "Aplicando config completo (prod + hmg HTTPS)"
    KEEP_HMG=true
else
    step "Aplicando config parcial (prod apenas — sem bloco HMG)"
    KEEP_HMG=false
fi

# Substituir placeholders de domínio e, opcionalmente, remover bloco HMG
python3 - "$NGINX_CONF_SRC" "$NGINX_CONF_DEST" "$DOMAIN_PROD" "$DOMAIN_HMG" "$KEEP_HMG" << 'PYEOF'
import sys
src, dst, domain_prod, domain_hmg, keep_hmg = \
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == "true"

with open(src) as f:
    content = f.read()

content = content.replace("__DOMAIN_PROD__", domain_prod)
content = content.replace("__DOMAIN_HMG__", domain_hmg)

if not keep_hmg:
    marker = "# ── HTTPS — Homologação"
    idx = content.find(marker)
    if idx != -1:
        content = content[:idx].rstrip() + "\n"
        print("Bloco HMG removido (cert ainda não existe)")
    else:
        print("Bloco HMG não encontrado no template")

with open(dst, 'w') as f:
    f.write(content)
PYEOF

################################################################################
# Ativar arch-analyzer, desativar default (evita conflito de default_server)
################################################################################

ln -sf "$NGINX_CONF_DEST" /etc/nginx/sites-enabled/arch-analyzer 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

################################################################################
# Validar e recarregar
################################################################################

if nginx -t 2>&1; then
    systemctl reload nginx
    ok "Nginx recarregado com sucesso"
else
    wrn "Config inválido — restaurando backup..."
    [ -f "${BACKUP:-}" ] && cp "$BACKUP" "$NGINX_CONF_DEST" && systemctl reload nginx
    err "Falha na validação do Nginx — verifique $NGINX_CONF_DEST"
fi

# Garantir que Nginx está habilitado para reiniciar com o sistema
systemctl enable nginx --quiet 2>/dev/null || true

echo ""
if [ "$WITH_HMG" = true ]; then
    ok "Nginx configurado para prod + hmg"
    inf "Produção    : https://${DOMAIN_PROD}"
    inf "Homologação : https://${DOMAIN_HMG}"
else
    ok "Nginx configurado para produção"
    inf "Produção: https://${DOMAIN_PROD}"
    inf "Homologação HTTPS: execute setup-ssl-hmg.sh para habilitar"
fi
