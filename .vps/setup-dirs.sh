#!/bin/bash
# setup-dirs.sh — Clona/atualiza o repositório nos diretórios de deploy
#
# Uso: sudo bash setup-dirs.sh [--token GITHUB_PAT]
#   --token  Personal Access Token do GitHub (necessário se repo for privado)
#
# Cria:
#   /opt/arch-analyzer/prod/  ← branch main
#   /opt/arch-analyzer/hmg/   ← branch hmg

set -e
source "$(dirname "$0")/lib.sh"
require_root

################################################################################
# Args — $GITHUB_TOKEN de env var (GitHub Actions) ou --token CLI
################################################################################

# GITHUB_TOKEN já pode estar no ambiente (injetado pelo Actions ou exportado manualmente)
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --token) GITHUB_TOKEN="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Monta URL (com ou sem token para repo privado)
if [ -n "$GITHUB_TOKEN" ]; then
    CLONE_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/bwasistemas/hackathon.git"
else
    CLONE_URL="$REPO_URL"
fi

################################################################################
# Clone / update
################################################################################

hdr "Diretórios de Deploy"

for ENV in prod hmg; do
    BRANCH="main"
    [ "$ENV" = "hmg" ] && BRANCH="hmg"
    DEPLOY_DIR="$BASE_DIR/$ENV"

    step "Ambiente $ENV → $DEPLOY_DIR (branch: $BRANCH)"
    mkdir -p "$DEPLOY_DIR"

    if [ -d "$DEPLOY_DIR/.git" ]; then
        inf "Repositório já existe — atualizando para origin/$BRANCH..."
        git -C "$DEPLOY_DIR" remote set-url origin "$CLONE_URL" 2>/dev/null || true
        git -C "$DEPLOY_DIR" fetch origin "$BRANCH" --quiet
        git -C "$DEPLOY_DIR" reset --hard "origin/$BRANCH" --quiet
        ok "$ENV atualizado para $(git -C "$DEPLOY_DIR" rev-parse --short HEAD)"
    else
        inf "Clonando branch $BRANCH em $DEPLOY_DIR..."
        if git clone --branch "$BRANCH" --depth 1 "$CLONE_URL" "$DEPLOY_DIR" --quiet; then
            ok "$ENV clonado ($(git -C "$DEPLOY_DIR" rev-parse --short HEAD))"
        else
            wrn "Clone falhou. Se o repo é privado, passe um token:"
            wrn "  sudo bash setup-dirs.sh --token ghp_SEU_TOKEN"
            exit 1
        fi
    fi
done

ok "Diretorios prontos em $BASE_DIR/"

# Transfere propriedade ao usuario que invocou sudo (usuario SSH do CI)
if [ -n "${SUDO_USER:-}" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$BASE_DIR"
    ok "Propriedade de $BASE_DIR transferida para $SUDO_USER"
fi
