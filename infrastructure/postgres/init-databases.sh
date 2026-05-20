#!/bin/bash
# Runs once on first PostgreSQL init (data dir empty).
# Creates the dedicated database for report-service.
# arch_uploads is created automatically by POSTGRES_DB env var.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE arch_reports OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = 'arch_reports'
    )\gexec
EOSQL

echo "init-databases.sh: arch_reports ready."
