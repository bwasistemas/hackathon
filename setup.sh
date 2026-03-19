#!/bin/bash

# ============================================
# Arch Analyzer - Setup Script
# Sobe todos os serviços do sistema
# ============================================

set -e

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Banner
show_banner() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                                                           ║"
    echo "║   🏗️  Arch Analyzer - Sistema de Análise de Diagramas     ║"
    echo "║                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
}

# Verificar pré-requisitos
check_requirements() {
    log_info "Verificando pré-requisitos..."
    
    # Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker não está instalado!"
        exit 1
    fi
    log_success "Docker encontrado: $(docker --version)"
    
    # Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose não está instalado!"
        exit 1
    fi
    
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    log_success "Docker Compose encontrado"
    
    # Verificar Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon não está rodando!"
        log_info "Execute: sudo systemctl start docker"
        exit 1
    fi
    log_success "Docker daemon está rodando"
}

# Configurar ambiente
setup_environment() {
    log_info "Configurando ambiente..."
    
    cd "$(dirname "$0")"
    
    # Criar .env se não existir
    if [ ! -f "infrastructure/.env" ]; then
        log_info "Criando arquivo .env..."
        cp infrastructure/.env.example infrastructure/.env
        log_warning "Arquivo .env criado! Edite com suas credenciais."
    else
        log_info "Arquivo .env já existe"
    fi
}

# Construir imagens
build_images() {
    log_info "Construindo imagens Docker..."
    
    cd infrastructure
    
    $COMPOSE_CMD build --parallel
    log_success "Imagens construídas"
}

# Subir serviços
start_services() {
    log_info "Subindo serviços..."
    
    $COMPOSE_CMD up -d
    
    log_success "Serviços iniciados!"
}

# Verificar status
check_status() {
    log_info "Verificando status dos serviços..."
    echo ""
    
    cd infrastructure
    $COMPOSE_CMD ps
    
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                    STATUS DOS SERVIÇOS                   ║"
    echo "╠═══════════════════════════════════════════════════════════╣"
    echo "║                                                           ║"
    echo "║   🌐 Frontend SPA          → http://localhost:8051       ║"
    echo "║   📚 Upload API           → http://localhost:8001/docs   ║"
    echo "║   🤖 AI Service           → http://localhost:8003/docs   ║"
    echo "║   📊 Report Service       → http://localhost:8004/docs   ║"
    echo "║   🐰 RabbitMQ             → http://localhost:15672       ║"
    echo "║   📈 Prometheus           → http://localhost:9090        ║"
    echo "║   📉 Grafana              → http://localhost:3000        ║"
    echo "║   🗄️  PostgreSQL          → localhost:5432               ║"
    echo "║                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
}

# Aguardar serviços ficarem prontos
wait_for_services() {
    log_info "Aguardando serviços ficarem prontos..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        echo -ne "\r[${attempt}/${max_attempts}] Verificando..."
        
        # Verifica frontend
        if curl -s http://localhost:8051 > /dev/null 2>&1; then
            log_success "Frontend pronto!"
            break
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo ""
    
    if [ $attempt -gt $max_attempts ]; then
        log_warning "Alguns serviços podem ainda estar iniciando..."
    fi
}

# Mostrar ajuda
show_help() {
    echo ""
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos:"
    echo "  start     Inicia todos os serviços (padrão)"
    echo "  stop      Para todos os serviços"
    echo "  restart   Reinicia todos os serviços"
    echo "  logs      Mostra logs de todos os serviços"
    echo "  status    Mostra status dos serviços"
    echo "  build     Reconstrói as imagens Docker"
    echo "  clean     Remove todos os containers e volumes"
    echo "  help      Mostra esta ajuda"
    echo ""
}

# Parar serviços
stop_services() {
    log_info "Parando serviços..."
    cd infrastructure
    $COMPOSE_CMD down
    log_success "Serviços parados!"
}

# Reiniciar serviços
restart_services() {
    stop_services
    start_services
}

# Mostrar logs
show_logs() {
    cd infrastructure
    $COMPOSE_CMD logs -f
}

# Limpar tudo
clean_all() {
    log_warning "Removendo containers e volumes..."
    cd infrastructure
    $COMPOSE_CMD down -v --remove-orphans
    log_success "Limpeza completa!"
}

# Main
main() {
    cd "$(dirname "$0")"
    
    case "${1:-start}" in
        start)
            show_banner
            check_requirements
            setup_environment
            build_images
            start_services
            wait_for_services
            check_status
            ;;
        stop)
            show_banner
            stop_services
            ;;
        restart)
            show_banner
            restart_services
            wait_for_services
            check_status
            ;;
        logs)
            show_logs
            ;;
        status)
            check_status
            ;;
        build)
            show_banner
            check_requirements
            build_images
            ;;
        clean)
            show_banner
            clean_all
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Comando desconhecido: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"