#!/bin/bash
# lib.sh — Funções compartilhadas entre os scripts .vps/
# Uso: source "$(dirname "$0")/lib.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()  { echo -e "${GREEN}✓ $*${NC}"; }
err() { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }
wrn() { echo -e "${YELLOW}⚠ $*${NC}"; }
inf() { echo -e "${BLUE}ℹ $*${NC}"; }
hdr() { echo -e "\n${BOLD}${BLUE}═══ $* ═══${NC}\n"; }
step(){ echo -e "${CYAN}→ $*${NC}"; }

require_root() {
    [ "$EUID" -eq 0 ] || err "Execute com sudo: sudo $0 $*"
}

require_cmd() {
    command -v "$1" &>/dev/null || err "Comando não encontrado: $1 — execute setup-vps.sh primeiro"
}

# Verifica se um serviço systemd está ativo
service_active() { systemctl is-active --quiet "$1"; }

# Gera senha aleatória segura
gen_secret() { python3 -c "import secrets; print(secrets.token_urlsafe(${1:-32}))"; }

# Lê uma linha do .env
env_get() {
    local file="$1" key="$2"
    grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

# Define/atualiza uma chave no .env
env_set() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Prompt interativo com valor padrão. Retorna via stdout.
# Uso: val=$(ask "Descrição" "default")
ask() {
    local prompt="$1" default="$2"
    local display_default=""
    [ -n "$default" ] && display_default=" [${default}]"
    read -rp "$(echo -e "${CYAN}  ${prompt}${display_default}: ${NC}")" val
    echo "${val:-$default}"
}

# Prompt para senha (sem echo). Retorna via stdout.
ask_secret() {
    local prompt="$1"
    read -rsp "$(echo -e "${CYAN}  ${prompt}: ${NC}")" val
    echo ""  # newline after hidden input
    echo "$val"
}

# Prompt para senha com geração automática opcional
ask_or_generate() {
    local prompt="$1"
    local len="${2:-32}"
    echo -e "${CYAN}  ${prompt}${NC}"
    echo -e "${YELLOW}  Pressione Enter para gerar automaticamente, ou digite o valor:${NC}"
    read -rsp "  → " val
    echo ""
    if [ -z "$val" ]; then
        val=$(gen_secret "$len")
        echo -e "${GREEN}  Gerado: ${val}${NC}"
    fi
    echo "$val"
}

# Verifica propagação de DNS (retorna 0 se IP bate, 1 caso contrário)
check_dns() {
    local domain="$1"
    local server_ip
    server_ip=$(curl -s -4 --max-time 5 ifconfig.me \
        || curl -s -4 --max-time 5 api.ipify.org || echo "")
    local domain_ip
    domain_ip=$(getent hosts "$domain" 2>/dev/null | awk '{print $1}' | head -1 || echo "")

    if [ -z "$domain_ip" ]; then
        wrn "DNS $domain ainda não resolve"
        return 1
    elif [ "$server_ip" = "$domain_ip" ]; then
        ok "DNS $domain → $server_ip ✓"
        return 0
    else
        wrn "DNS $domain → $domain_ip (esperado: $server_ip)"
        return 1
    fi
}

# Caminhos padrão do projeto
BASE_DIR="/opt/arch-analyzer"
PROD_DIR="$BASE_DIR/prod"
HMG_DIR="$BASE_DIR/hmg"
REPO_URL="https://github.com/bwasistemas/hackathon.git"

# Domínios — lidos de variáveis de ambiente (GitHub Actions vars.*) com fallback
DOMAIN_PROD="${DOMAIN_PROD:-archanalyzer.brunoretiro.com.br}"
DOMAIN_HMG="${DOMAIN_HMG:-archanalyzerhmg.brunoretiro.com.br}"

NGINX_CONF_DEST="/etc/nginx/sites-available/arch-analyzer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_CONF_SRC="$SCRIPT_DIR/nginx-archanalyzer.conf"
