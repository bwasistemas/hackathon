#!/bin/bash
# Runs once on first PostgreSQL init (data dir empty).
# Creates both dedicated databases idempotently.
# On existing PVCs this script does NOT run — use postgres-setup (docker-compose)
# or init containers (k8s) to handle the migration case.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE arch_uploads OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = 'arch_uploads'
    )\gexec

    SELECT 'CREATE DATABASE arch_reports OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = 'arch_reports'
    )\gexec
EOSQL

echo "init-databases.sh: arch_uploads and arch_reports ready."
