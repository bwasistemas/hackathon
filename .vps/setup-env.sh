#!/bin/bash
# setup-env.sh — Cria/atualiza os arquivos .env de produção e homologação
#
# Uso: sudo bash setup-env.sh [--non-interactive]
#   --non-interactive  Gera todos os secrets automaticamente (sem perguntas)
#                      Útil para CI ou recriação rápida.
#
# O script:
#   1. Copia .env.example como base
#   2. Solicita apenas as credenciais que PRECISAM ser definidas manualmente
#   3. Gera automaticamente JWT_SECRET_KEY e MINIO_SECRET_KEY
#   4. Define as portas corretas para cada ambiente
#   5. É idempotente — não sobrescreve se o .env já existir (usa --force para forçar)

set -e
source "$(dirname "$0")/lib.sh"
require_root

################################################################################
# Args
################################################################################

NON_INTERACTIVE=false
FORCE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --force) FORCE=true; shift ;;
        *) shift ;;
    esac
done

################################################################################
# Helpers
################################################################################

# Cria .env a partir do .env.example (idempotente)
init_env() {
    local env_file="$1"
    local deploy_dir
    deploy_dir="$(dirname "$env_file")"

    if [ -f "$env_file" ] && [ "$FORCE" = false ]; then
        wrn ".env já existe: $env_file (use --force para recriar)"
        return 1
    fi

    local example="$deploy_dir/.env.example"
    if [ ! -f "$example" ]; then
        err ".env.example não encontrado em $deploy_dir — execute setup-dirs.sh primeiro"
    fi

    cp "$example" "$env_file"
    inf "Criado $env_file a partir do .env.example"
    return 0
}

# Solicita credencial ou gera automaticamente
set_credential() {
    local file="$1" key="$2" description="$3" auto_generate="$4"

    if [ "$NON_INTERACTIVE" = true ] || [ "$auto_generate" = "auto" ]; then
        local generated
        generated=$(gen_secret 32)
        env_set "$file" "$key" "$generated"
        inf "$key gerado automaticamente"
        return
    fi

    local current
    current=$(env_get "$file" "$key")

    # Já tem valor real? Pula.
    if [ -n "$current" ] && \
       [ "$current" != "change-me-in-production" ] && \
       [ "$current" != "your-openai-api-key-here" ] && \
       [ "$current" != "replace-with-a-64-char-random-string" ]; then
        inf "$key já configurado — mantido"
        return
    fi

    echo -e "${YELLOW}  $description${NC}"
    local val
    val=$(ask_secret "  $key")
    if [ -z "$val" ] && [ "$auto_generate" = "generate_if_empty" ]; then
        val=$(gen_secret 32)
        inf "  $key gerado: $val"
    fi
    [ -n "$val" ] && env_set "$file" "$key" "$val"
}

################################################################################
# Configuração de um ambiente
################################################################################

configure_env() {
    local env_name="$1"   # "prod" ou "hmg"
    local env_file="$2"

    hdr "Configurando .env — $env_name"

    init_env "$env_file" || return 0   # retorna se já existe e não --force

    # ── Secrets (prompt ou auto-gerado) ──────────────────────────────────────

    echo ""
    echo -e "${BOLD}Credenciais obrigatórias para $env_name:${NC}"
    echo -e "${YELLOW}(Enter = gerar automaticamente para senhas, obrigatório para APIs)${NC}"
    echo ""

    set_credential "$env_file" "POSTGRES_PASSWORD"  "Senha do PostgreSQL"              "generate_if_empty"
    set_credential "$env_file" "RABBITMQ_PASSWORD"  "Senha do RabbitMQ"                "generate_if_empty"
    set_credential "$env_file" "MINIO_SECRET_KEY"   "Secret Key do MinIO"              "generate_if_empty"
    set_credential "$env_file" "JWT_SECRET_KEY"     "JWT Secret Key (token de sessão)" "generate_if_empty"
    set_credential "$env_file" "ADMIN_PASSWORD"     "Senha do admin da aplicação"      "generate_if_empty"
    set_credential "$env_file" "GRAFANA_PASSWORD"   "Senha do Grafana"                 "generate_if_empty"

    if [ "$NON_INTERACTIVE" = false ]; then
        echo ""
        echo -e "${YELLOW}  OPENAI_API_KEY (obrigatório — não pode ser gerado automaticamente):${NC}"
        local api_key
        api_key=$(ask_secret "  OPENAI_API_KEY")
        [ -n "$api_key" ] && env_set "$env_file" "OPENAI_API_KEY" "$api_key"
    fi

    # ── Valores fixos por ambiente ────────────────────────────────────────────

    # ALLOWED_ORIGINS
    if [ "$env_name" = "prod" ]; then
        env_set "$env_file" "ALLOWED_ORIGINS" "https://${DOMAIN_PROD}"
    else
        env_set "$env_file" "ALLOWED_ORIGINS" "https://${DOMAIN_HMG}"
    fi

    # IMAGE_TAG inicial
    env_set "$env_file" "IMAGE_TAG" "$env_name"

    # Evitar conflito Portainer (porta 9000) vs MinIO
    env_set "$env_file" "MINIO_API_HOST_PORT"     "9010"
    env_set "$env_file" "MINIO_CONSOLE_HOST_PORT" "9011"

    # Portas do host para HMG (deslocadas para não conflitar com prod)
    if [ "$env_name" = "hmg" ]; then
        env_set "$env_file" "FRONTEND_HOST_PORT"            "8151"
        env_set "$env_file" "POSTGRES_HOST_PORT"            "5433"
        env_set "$env_file" "RABBITMQ_HOST_PORT"            "5673"
        env_set "$env_file" "RABBITMQ_MANAGEMENT_HOST_PORT" "15673"
        env_set "$env_file" "RABBITMQ_PROMETHEUS_HOST_PORT" "15693"
        env_set "$env_file" "UPLOAD_HOST_PORT"              "8101"
        env_set "$env_file" "AI_HOST_PORT"                  "8103"
        env_set "$env_file" "REPORT_HOST_PORT"              "8104"
        env_set "$env_file" "PROMETHEUS_HOST_PORT"          "9091"
        env_set "$env_file" "LOKI_HOST_PORT"                "3101"
        env_set "$env_file" "GRAFANA_HOST_PORT"             "3001"
    fi

    ok ".env de $env_name configurado: $env_file"

    # Resumo de valores gerados
    echo ""
    echo -e "${CYAN}Valores configurados em $env_name:${NC}"
    for k in POSTGRES_PASSWORD RABBITMQ_PASSWORD JWT_SECRET_KEY ADMIN_PASSWORD GRAFANA_PASSWORD MINIO_SECRET_KEY; do
        local v
        v=$(env_get "$env_file" "$k")
        [ -n "$v" ] && echo -e "  ${BOLD}$k${NC} = ${v:0:20}..."
    done
    echo ""
}

################################################################################
# Main
################################################################################

PROD_ENV="$PROD_DIR/infrastructure/.env"
HMG_ENV="$HMG_DIR/infrastructure/.env"

configure_env "prod" "$PROD_ENV"
configure_env "hmg"  "$HMG_ENV"

echo ""
ok "Arquivos .env configurados."
echo -e "${YELLOW}Importante: guarde as senhas geradas em um gerenciador de senhas.${NC}"
echo -e "${YELLOW}Os .env NÃO devem ser commitados no repositório.${NC}"
