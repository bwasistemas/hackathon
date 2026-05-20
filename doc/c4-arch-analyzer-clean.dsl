workspace "Arch Analyzer" "Análise automatizada de diagramas de arquitetura com IA" {

    model {

        // Pessoa
        analista = person "Analista" "Envia diagramas, consulta relatórios e avalia análises"

        // Externos
        openRouter = softwareSystem "OpenRouter" "DeepSeek v3.2 (análise) + Gemma 4 26B (OCR multimodal)" {
            tags "External System"
        }

        github = softwareSystem "GitHub / GHCR" "CI/CD: testes → build → push GHCR → deploy na VPS via kubectl" {
            tags "External System"
        }

        // Sistema
        archAnalyzer = softwareSystem "Arch Analyzer" "Recebe diagramas, processa via OCR + swarm LLM e exibe relatório estruturado" {

            frontend = container "Frontend" "SPA Nginx com proxy para as APIs e health checks de infra" "Nginx :8051" {
                tags "Web Browser"
            }

            uploadService = container "Upload Service" "Recebe arquivos, armazena no MinIO, publica diagram.upload e consome diagram.result" "FastAPI :8001" {
                tags "Service"
            }

            aiService = container "AI Service" "OCR multimodal + swarm Strands (DeepSeek). Publica diagram.result. KEDA autoscaling no k8s." "FastAPI :8003" {
                tags "Service"
            }

            reportService = container "Report Service" "Relatórios e feedback. Lê uploads via HTTP do Upload Service (JWT s2s)." "FastAPI :8004" {
                tags "Service"
            }

            rabbitmq = container "RabbitMQ" "diagram.upload: upload→ai  |  diagram.result: ai→upload" "RabbitMQ 3.13 :5672" {
                tags "Message Broker"
            }

            minio = container "MinIO" "Object storage S3 dos arquivos enviados pelos usuários" "MinIO :9000" {
                tags "File System"
            }

            group "PostgreSQL 16 — mesma instância" {

                uploadDb = container "arch_uploads" "Tabelas: uploads + users. Dono: Upload Service." "PostgreSQL :5432" {
                    tags "Database"
                }

                reportsDb = container "arch_reports" "Tabela: feedback. Dono: Report Service." "PostgreSQL :5432" {
                    tags "Database"
                }
            }

            group "Observabilidade" {

                prometheus = container "Prometheus" "Scrape /metrics dos pods via annotations" "Prometheus :9090" {
                    tags "Monitoring"
                }

                grafana = container "Grafana" "Dashboards: Overview (métricas) e Logs (Loki)" "Grafana :3000" {
                    tags "Monitoring"
                }

                loki = container "Loki" "Agregação de logs dos containers" "Loki :3100" {
                    tags "Monitoring"
                }

                promtail = container "Promtail" "Coleta logs via Docker socket (Compose) ou /var/log/pods (k8s)" "Promtail 3.3" {
                    tags "Monitoring"
                }

                postgresExporter = container "postgres-exporter" "Métricas do PostgreSQL para o Prometheus (somente Compose)" "pg-exporter :9187" {
                    tags "Monitoring"
                }
            }
        }

        // ── Pessoa
        analista -> frontend "Upload, status, relatório e feedback" "HTTPS"

        // ── Frontend → APIs
        frontend -> uploadService "/upload-service/ — upload, token, listagem" "HTTP + JWT"
        frontend -> aiService "/ai-service/ — health, analyze" "HTTP"
        frontend -> reportService "/report-service/ — reports, feedback, stats" "HTTP + JWT"
        frontend -> rabbitmq "/infra-health/rabbitmq" "HTTP"
        frontend -> grafana "/infra-health/grafana" "HTTP"
        frontend -> prometheus "/infra-health/prometheus" "HTTP"
        frontend -> loki "/infra-health/loki" "HTTP"

        // ── Upload Service
        uploadService -> uploadDb "INSERT / UPDATE / SELECT" "asyncpg"
        uploadService -> minio "PUT arquivo" "S3 API"
        uploadService -> rabbitmq "Publica diagram.upload" "AMQP"
        rabbitmq -> uploadService "Entrega diagram.result" "AMQP"

        // ── AI Service
        rabbitmq -> aiService "Entrega diagram.upload" "AMQP"
        aiService -> minio "GET arquivo para OCR" "S3 API"
        aiService -> openRouter "OCR Gemma + análise DeepSeek (Strands)" "HTTPS"
        aiService -> rabbitmq "Publica diagram.result" "AMQP"

        // ── Report Service
        reportService -> uploadService "GET /uploads, /stats/uploads (JWT s2s)" "HTTP + JWT"
        reportService -> reportsDb "INSERT / SELECT feedback" "asyncpg"
        reportService -> minio "GET arquivo (attachment)" "S3 API"

        // ── Observabilidade
        prometheus -> uploadService "Scrape /metrics :8001" "HTTP"
        prometheus -> aiService "Scrape /metrics :8003" "HTTP"
        prometheus -> reportService "Scrape /metrics :8004" "HTTP"
        prometheus -> rabbitmq "Scrape /metrics :15692" "HTTP"
        prometheus -> postgresExporter "Scrape /metrics" "HTTP"
        postgresExporter -> uploadDb "Métricas do PostgreSQL" "TCP"
        grafana -> prometheus "Datasource PromQL" "HTTP"
        grafana -> loki "Datasource LogQL" "HTTP"
        promtail -> loki "Push de logs" "HTTP"

        // ── CI/CD
        github -> archAnalyzer "main → arch-prod  |  hmg → arch-hmg" "GitHub Actions"

        // ── Deploy Local (Docker Compose)
        deploymentEnvironment "Local" {
            deploymentNode "Docker Host" "Linux / macOS / WSL2" "Docker Engine" {
                deploymentNode "arch-network" "" "Docker Bridge" {
                    containerInstance frontend
                    containerInstance uploadService
                    containerInstance aiService
                    containerInstance reportService
                    containerInstance rabbitmq
                    containerInstance minio
                    containerInstance uploadDb
                    containerInstance reportsDb
                    containerInstance prometheus
                    containerInstance grafana
                    containerInstance loki
                    containerInstance promtail
                    containerInstance postgresExporter
                }
            }
        }

        // ── Deploy Produção (Kubernetes / Kind na VPS)
        deploymentEnvironment "Producao" {
            deploymentNode "VPS Ubuntu" "" "Ubuntu Linux" {

                deploymentNode "Nginx" "SSL + proxy para NodePorts do Kind" "Nginx + certbot" {
                }

                deploymentNode "Kind Cluster" "" "Kubernetes in Docker" {

                    deploymentNode "arch-prod / arch-hmg" "Namespace da aplicação (rotacionado a cada push)" "Namespace" {

                        deploymentNode "frontend" "" "Deployment" {
                            containerInstance frontend
                        }
                        deploymentNode "upload-service" "initContainer cria arch_uploads" "Deployment" {
                            containerInstance uploadService
                        }
                        deploymentNode "ai-service" "KEDA: escala pela fila diagram.upload (min 1, max N)" "Deployment" {
                            containerInstance aiService
                        }
                        deploymentNode "report-service" "initContainer cria arch_reports" "Deployment" {
                            containerInstance reportService
                        }
                        deploymentNode "rabbitmq" "PVC 5Gi" "StatefulSet" {
                            containerInstance rabbitmq
                        }
                        deploymentNode "minio" "PVC 20Gi" "StatefulSet" {
                            containerInstance minio
                        }
                        deploymentNode "postgres" "PVC 10Gi — arch_uploads + arch_reports" "StatefulSet" {
                            containerInstance uploadDb
                            containerInstance reportsDb
                        }
                    }

                    deploymentNode "arch-geral" "Observabilidade compartilhada (não rotacionada)" "Namespace" {

                        deploymentNode "prometheus" "ClusterRole p/ auto-descoberta de pods" "Deployment" {
                            containerInstance prometheus
                        }
                        deploymentNode "grafana" "PVC grafana-data" "Deployment" {
                            containerInstance grafana
                        }
                        deploymentNode "loki" "PVC loki-data" "Deployment" {
                            containerInstance loki
                        }
                        deploymentNode "promtail" "Lê /var/log/pods/ do nó" "DaemonSet" {
                            containerInstance promtail
                        }
                    }
                }
            }
        }
    }

    views {

        // Nível 1 — Contexto
        systemContext archAnalyzer "SystemContext" {
            title "Contexto do Sistema"
            include *
            autoLayout tb 300 200
        }

        // Nível 2 — Containers (fluxo da esquerda para a direita)
        container archAnalyzer "Containers" {
            title "Visão de Containers"
            include *
            autoLayout lr 350 200
        }

        // Nível 3 — Upload e Análise
        dynamic archAnalyzer "UploadFlow" {
            title "Fluxo: Upload e Análise"

            analista -> frontend "1. Envia arquivo"
            frontend -> uploadService "2. POST /upload"
            uploadService -> minio "3. PUT arquivo"
            uploadService -> uploadDb "4. INSERT status=RECEIVED"
            uploadService -> rabbitmq "5. Publica diagram.upload"
            rabbitmq -> aiService "6. Entrega diagram.upload"
            aiService -> rabbitmq "7. Publica status=PROCESSING"
            rabbitmq -> uploadService "8. Entrega PROCESSING"
            uploadService -> uploadDb "9. UPDATE status=PROCESSING"
            aiService -> minio "10. GET arquivo"
            aiService -> openRouter "11. OCR + análise LLM"
            aiService -> rabbitmq "12. Publica status=DONE + payload"
            rabbitmq -> uploadService "13. Entrega DONE"
            uploadService -> uploadDb "14. UPDATE status=DONE + JSON"

            autoLayout tb 150 150
        }

        // Nível 3 — Relatório e Feedback
        dynamic archAnalyzer "ReportFlow" {
            title "Fluxo: Relatório e Feedback"

            analista -> frontend "1. Abre relatório"
            frontend -> reportService "2. GET /reports/{id}"
            reportService -> uploadService "3. GET /uploads/{id}"
            uploadService -> uploadDb "4. SELECT upload"
            uploadService -> reportService "5. UploadDetail"
            reportService -> frontend "6. ReportResponse"
            analista -> frontend "7. Envia feedback"
            frontend -> reportService "8. POST /feedback"
            reportService -> uploadService "9. Verifica existência"
            reportService -> reportsDb "10. INSERT feedback"

            autoLayout tb 150 150
        }

        // Nível 3 — Estatísticas
        dynamic archAnalyzer "StatsFlow" {
            title "Fluxo: Estatísticas Combinadas"

            analista -> frontend "1. Acessa estatísticas"
            frontend -> reportService "2. GET /stats"
            reportService -> uploadService "3. GET /stats/uploads"
            uploadService -> uploadDb "4. COUNT por status"
            uploadService -> reportService "5. {total, by_status}"
            reportService -> reportsDb "6. AVG(rating) + COUNT"
            reportService -> frontend "7. Statistics"

            autoLayout tb 150 150
        }

        // Deploy — Docker Compose
        deployment archAnalyzer "Local" "LocalDeployment" {
            title "Deploy: Docker Compose (Local)"
            include *
            autoLayout tb 250 200
        }

        // Deploy — Kubernetes
        deployment archAnalyzer "Producao" "KubernetesDeployment" {
            title "Deploy: Kubernetes na VPS"
            include *
            autoLayout tb 250 200
        }

        // Estilos
        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "External System" {
                background #666666
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Web Browser" {
                shape WebBrowser
                background #1565C0
                color #ffffff
            }
            element "Service" {
                background #1976D2
                color #ffffff
            }
            element "Message Broker" {
                shape Pipe
                background #BF360C
                color #ffffff
            }
            element "Database" {
                shape Cylinder
                background #1A5276
                color #ffffff
            }
            element "File System" {
                shape Folder
                background #00695C
                color #ffffff
            }
            element "Monitoring" {
                background #37474F
                color #ffffff
            }
            relationship "Relationship" {
                fontSize 11
                color #707070
            }
        }
    }
}
