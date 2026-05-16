#!/bin/bash
# setup-deploy.sh — Orchestrador de setup completo do CD na VPS
#
# Executa em sequência:
#   1. setup-dirs.sh    → clona repositório (prod e hmg)
#   2. setup-env.sh     → cria arquivos .env (prompts mínimos)
#   3. setup-nginx.sh   → configura Nginx para produção
#   4. setup-ssl-hmg.sh → gera SSL para archanalyzerhmg.brunoretiro.com.br
#
# Variáveis de ambiente (têm precedência sobre os argumentos):
#   LETSENCRYPT_EMAIL   Email para o certbot (secret do GitHub: LETSENCRYPT_EMAIL)
#   GITHUB_TOKEN        Token para clonar repo privado (injetado pelo GitHub Actions)
#
# Uso manual (VPS diretamente):
#   sudo ./setup-deploy.sh [opções]
#
# Uso via GitHub Actions (setup-vps.yml):
#   As variáveis são injetadas automaticamente a partir dos secrets.
#
# Opções:
#   --email EMAIL        Email Let's Encrypt (alternativa à var LETSENCRYPT_EMAIL)
#   --token TOKEN        GitHub token (alternativa à var GITHUB_TOKEN)
#   --non-interactive    Gera todos os secrets automaticamente, sem perguntas
#   --skip-dns-check     Pula verificação de DNS para o cert HMG
#   --skip-ssl-hmg       Não gera cert HMG agora (faça depois com setup-ssl-hmg.sh)
#   --force-env          Recria os .env mesmo se já existirem

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
require_root

################################################################################
# Args — env vars têm precedência; CLI é fallback
################################################################################

# Lê de env var primeiro (injetada pelo GitHub Actions via secrets)
EMAIL="${LETSENCRYPT_EMAIL:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
NON_INTERACTIVE=false
SKIP_DNS=false
SKIP_SSL_HMG=false
FORCE_ENV=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --email)              EMAIL="$2"; shift 2 ;;
        --token)              GITHUB_TOKEN="$2"; shift 2 ;;
        --non-interactive)    NON_INTERACTIVE=true; shift ;;
        --skip-dns-check)     SKIP_DNS=true; shift ;;
        --skip-ssl-hmg)       SKIP_SSL_HMG=true; shift ;;
        --force-env)          FORCE_ENV=true; shift ;;
        -*) wrn "Opção desconhecida: $1"; shift ;;
        *)  [ -z "$EMAIL" ] && EMAIL="$1"; shift ;;
    esac
done

if [ -z "$EMAIL" ]; then
    err "Email não definido. Use --email ou defina a variável LETSENCRYPT_EMAIL."
fi

################################################################################
# Header
################################################################################

clear 2>/dev/null || true
echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║      Arch Analyzer — Setup CD na VPS                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Email      : ${YELLOW}$EMAIL${NC}"
echo -e "  Produção   : ${GREEN}https://${DOMAIN_PROD}${NC}"
echo -e "  Homologação: ${GREEN}https://${DOMAIN_HMG}${NC}"
echo ""
echo -e "  Etapas:"
echo -e "    1. Clone/atualização do repositório"
echo -e "    2. Criação dos arquivos .env"
echo -e "    3. Configuração do Nginx"
echo -e "    4. Certificado SSL para HMG"
echo ""

################################################################################
# Etapa 1 — Diretórios / Clone
################################################################################

hdr "1/4 — Repositório"

DIRS_ARGS=()
[ -n "$GITHUB_TOKEN" ] && DIRS_ARGS+=(--token "$GITHUB_TOKEN")
bash "$SCRIPT_DIR/setup-dirs.sh" "${DIRS_ARGS[@]}"

################################################################################
# Etapa 2 — Arquivos .env
################################################################################

hdr "2/4 — Configuração .env"

ENV_ARGS=()
[ "$NON_INTERACTIVE" = true ] && ENV_ARGS+=(--non-interactive)
[ "$FORCE_ENV" = true ]       && ENV_ARGS+=(--force)
bash "$SCRIPT_DIR/setup-env.sh" "${ENV_ARGS[@]}"

################################################################################
# Etapa 3 — Nginx (sem HMG por enquanto)
################################################################################

hdr "3/4 — Nginx"

bash "$SCRIPT_DIR/setup-nginx.sh"

################################################################################
# Etapa 4 — SSL HMG
################################################################################

hdr "4/4 — SSL Homologação"

if [ "$SKIP_SSL_HMG" = true ]; then
    wrn "SSL HMG ignorado (--skip-ssl-hmg)."
    inf "Execute depois: sudo bash $SCRIPT_DIR/setup-ssl-hmg.sh $EMAIL"
else
    SSL_ARGS=("$EMAIL")
    [ "$SKIP_DNS" = true ] && SSL_ARGS+=(--skip-dns-check)
    bash "$SCRIPT_DIR/setup-ssl-hmg.sh" "${SSL_ARGS[@]}" || {
        wrn "SSL HMG falhou (DNS ainda não propagado?)"
        inf "Execute depois: sudo bash $SCRIPT_DIR/setup-ssl-hmg.sh $EMAIL"
    }
fi

################################################################################
# Resumo final
################################################################################

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║             Setup Concluído ✓                        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BOLD}Próximos passos:${NC}"
echo ""
echo -e "  ${CYAN}1. Configure os Secrets e Variables no GitHub:${NC}"
echo -e "     https://github.com/bwasistemas/hackathon/settings/secrets/actions"
echo ""
echo -e "     ${BOLD}Secret                 Valor${NC}"
echo -e "     ──────────────────────────────────────────────────────────────"
echo -e "     VPS_HOST               $(curl -s -4 --max-time 5 ifconfig.me 2>/dev/null || echo '<IP_DA_VPS>')"
echo -e "     VPS_USER               $(whoami)"
echo -e "     VPS_SSH_KEY            conteúdo de ~/.ssh/id_ed25519 (ou chave dedicada)"
echo -e "     VPS_SSH_PORT           omita se for a porta 22"
echo -e "     LETSENCRYPT_EMAIL       ${EMAIL}"
echo -e "     POSTGRES_PASSWORD      <senha forte>"
echo -e "     RABBITMQ_PASSWORD      <senha forte>"
echo -e "     OPENAI_API_KEY         sk-..."
echo -e "     JWT_SECRET_KEY         <48+ chars aleatórios>"
echo -e "     ADMIN_PASSWORD         $ADMIN"
echo -e "     MINIO_SECRET_KEY       <senha forte>"
echo -e "     GRAFANA_PASSWORD       <senha forte>"
echo ""
echo -e "     ${YELLOW}O pipeline escreve esses valores no .env da VPS a cada deploy.${NC}"
echo ""
echo -e "  ${CYAN}2. Primeiro deploy:${NC}"
echo -e "     git push origin main  ← deploy de produção"
echo -e "     git push origin hmg   ← deploy de homologação"
echo ""
echo -e "  ${CYAN}3. Acesso:${NC}"
echo -e "     ${GREEN}Produção    : https://${DOMAIN_PROD}${NC}"
echo -e "     ${GREEN}Homologação : https://${DOMAIN_HMG}${NC}"
echo -e "     ${GREEN}Portainer   : https://${DOMAIN_PROD}/portainer/${NC}"
echo -e "     ${GREEN}Headlamp    : https://${DOMAIN_PROD}/k8s/${NC}"
echo ""
echo -e "  ${CYAN}4. Consulte o guia completo:${NC}"
echo -e "     $SCRIPT_DIR/GUIA-CD.md"
echo ""
