#!/bin/bash
# Security Configuration Validator
# This script validates security configurations across all services

set -e

echo "🔒 Security Configuration Validator"
echo "=================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env file exists
if [ ! -f "infrastructure/.env" ]; then
    echo -e "${RED}❌ infrastructure/.env not found${NC}"
    exit 1
fi

# Load environment variables
set -a
source infrastructure/.env
set +a

# Check JWT Secret Key
if [ "$JWT_SECRET_KEY" = "your-super-secure-jwt-secret-key-here-change-this-in-production" ]; then
    echo -e "${RED}❌ JWT_SECRET_KEY is using default value - CHANGE IN PRODUCTION${NC}"
else
    echo -e "${GREEN}✅ JWT_SECRET_KEY is configured${NC}"
fi

# Check CORS origins
if [ -z "$CORS_ALLOWED_ORIGINS" ]; then
    echo -e "${YELLOW}⚠️  CORS_ALLOWED_ORIGINS not set - using defaults${NC}"
else
    echo -e "${GREEN}✅ CORS_ALLOWED_ORIGINS configured${NC}"
fi

# Check log directory
if [ -z "$LOG_DIR" ]; then
    echo -e "${YELLOW}⚠️  LOG_DIR not set - using defaults${NC}"
else
    echo -e "${GREEN}✅ LOG_DIR configured${NC}"
fi

# Check database SSL
if [ "$DB_SSL_MODE" = "require" ]; then
    echo -e "${GREEN}✅ Database SSL enabled${NC}"
else
    echo -e "${YELLOW}⚠️  Database SSL not required${NC}"
fi

# Check MinIO security
if [ "$MINIO_SECURE" = "true" ] && [ "$MINIO_SSL" = "true" ]; then
    echo -e "${GREEN}✅ MinIO SSL enabled${NC}"
else
    echo -e "${YELLOW}⚠️  MinIO SSL not fully configured${NC}"
fi

# Check RabbitMQ security
if [ "$RABBITMQ_SSL" = "true" ]; then
    echo -e "${GREEN}✅ RabbitMQ SSL enabled${NC}"
else
    echo -e "${YELLOW}⚠️  RabbitMQ SSL not enabled${NC}"
fi

# Check if security headers are enabled
if [ "$SECURITY_HEADERS_ENABLED" = "true" ]; then
    echo -e "${GREEN}✅ Security headers enabled${NC}"
else
    echo -e "${YELLOW}⚠️  Security headers not enabled${NC}"
fi

# Check rate limiting
if [ -n "$UPLOAD_RATE_LIMIT" ] && [ -n "$REPORT_RATE_LIMIT" ] && [ -n "$AI_ANALYSIS_RATE_LIMIT" ]; then
    echo -e "${GREEN}✅ Rate limiting configured${NC}"
else
    echo -e "${YELLOW}⚠️  Rate limiting not fully configured${NC}"
fi

# Check Python syntax
echo ""
echo "🔍 Checking Python syntax..."
services=("upload-service" "ai-service" "report-service")

for service in "${services[@]}"; do
    if [ -f "services/$service/app/bootstrap.py" ]; then
        if python3 -m py_compile "services/$service/app/bootstrap.py" 2>/dev/null; then
            echo -e "${GREEN}✅ $service bootstrap.py syntax OK${NC}"
        else
            echo -e "${RED}❌ $service bootstrap.py syntax ERROR${NC}"
        fi
    fi
done

# Check if log directories exist
echo ""
echo "📁 Checking log directories..."
if [ -n "$LOG_DIR" ] && [ -d "$LOG_DIR" ]; then
    echo -e "${GREEN}✅ Log directory exists${NC}"
elif [ -n "$LOG_DIR" ]; then
    echo -e "${YELLOW}⚠️  Log directory does not exist - will be created at runtime${NC}"
else
    echo -e "${YELLOW}⚠️  Log directory not configured${NC}"
fi

echo ""
echo "🎯 Security validation complete!"
echo "Review any warnings above before deploying to production."