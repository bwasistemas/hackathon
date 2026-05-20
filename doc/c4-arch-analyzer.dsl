workspace "Arch Analyzer" "Sistema de análise automática de diagramas de arquitetura com IA — Hackathon FIAP 2026" {

    model {

        // ─── Pessoas ──────────────────────────────────────────────────────────────────
        analista = person "Analista" "Profissional ou estudante que envia diagramas de arquitetura (PNG, JPG, JPEG, PDF), acompanha o processamento, consulta o relatório estruturado e envia avaliação de feedback"

        // ─── Sistemas Externos ────────────────────────────────────────────────────────
        openRouter = softwareSystem "OpenRouter" "Gateway LLM compatível com API OpenAI. Dois modelos em uso: DeepSeek v3.2 para análise de arquitetura via swarm Strands (componentes, riscos, recomendações) e Gemma 4 26B para OCR multimodal. Endereço configurado via OPENAI_BASE_URL + OPENAI_API_KEY." {
            tags "External System"
        }

        github = softwareSystem "GitHub / GHCR" "Repositório de código (github.com/bwasistemas/hackathon) e Container Registry. GitHub Actions orquestra: testes unitários em paralelo → build e push das imagens para GHCR com tag branch-sha → deploy na VPS via SCP + SSH + kubectl." {
            tags "External System"
        }

        // ─── Sistema Principal ────────────────────────────────────────────────────────
        archAnalyzer = softwareSystem "Arch Analyzer" "Recebe diagramas de arquitetura (até 10 MB), processa de forma assíncrona via fila AMQP, aplica OCR multimodal com LLM e swarm de agentes para análise, persiste o resultado estruturado (componentes, riscos, resumo) e disponibiliza para consulta e feedback" {

            // ── Apresentação ──────────────────────────────────────────────────────────
            frontend = container "Frontend" "SPA estática (HTML + JS + CSS) servida pelo Nginx na porta 8051. Proxy reverso para as três APIs de negócio (prefixos /upload-service/, /ai-service/, /report-service/). Proxy de health check para RabbitMQ, Grafana, Prometheus e Loki via /infra-health/* na mesma origem — necessário para evitar bloqueio pelo CSP. Limite de upload: 12 MB no Nginx." "Nginx :8051" {
                tags "Web Browser"
            }

            // ── Serviços de Negócio ───────────────────────────────────────────────────
            uploadService = container "Upload Service" "Recebe arquivos (PNG, JPG, JPEG, PDF — até 10 MB), valida, armazena no MinIO, persiste metadados em arch_uploads com status inicial RECEIVED, publica evento na fila diagram.upload e consome respostas de diagram.result para atualizar o registro do upload. Único serviço que emite tokens JWT. Rate limiting via SlowAPI. Expõe endpoint /stats/uploads para o Report Service." "FastAPI + Python :8001" {
                tags "Service"
            }

            aiService = container "AI Service" "Consome fila diagram.upload (prefetch=1). Baixa o arquivo do MinIO. Executa OCR multimodal com LLM (Gemma 4 26B via OpenRouter) com fallback para Tesseract. Analisa com swarm multi-agente Strands: agentes de arquitetura, infraestrutura e desenvolvimento consolidam o resultado em JSON (components, risks, summary). Publica diagram.result. Sem acesso a banco de dados. Escala automaticamente via KEDA no Kubernetes." "FastAPI + Python :8003" {
                tags "Service"
            }

            reportService = container "Report Service" "Serve relatórios e coleta feedback. Lê dados de uploads via chamadas HTTP autenticadas ao Upload Service (JWT service-to-service, token renovado 60s antes do vencimento — não acessa banco de uploads diretamente). Persiste avaliações 1–5 com comentário no banco próprio arch_reports. Expõe endpoint /stats que combina contagens do Upload Service com estatísticas de feedback." "FastAPI + Python :8004" {
                tags "Service"
            }

            // ── Mensageria ────────────────────────────────────────────────────────────
            rabbitmq = container "RabbitMQ" "Broker AMQP que desacopla o upload do processamento de IA. Fila diagram.upload (durable): publicada pelo Upload Service, consumida pelo AI Service. Payload: {upload_id, filename, file_path, content_type}. Fila diagram.result (durable): publicada pelo AI Service, consumida pelo Upload Service. Payload: {upload_id, status, payload_json?, error_message?}. Interface de gerenciamento web em :15672. Métricas Prometheus em :15692." "RabbitMQ 3.13 :5672" {
                tags "Message Broker"
            }

            // ── Object Storage ────────────────────────────────────────────────────────
            minio = container "MinIO" "Object storage S3-compatible. Armazena os arquivos enviados pelos usuários. Upload Service grava via PUT; AI Service lê via GET para processar; Report Service lê via GET para servir o anexo original ao usuário. Bucket configurável via MINIO_BUCKET (padrão: fiap). Console web em :9001." "MinIO :9000 / console :9001" {
                tags "File System"
            }

            // ── Bancos de Dados ───────────────────────────────────────────────────────
            group "PostgreSQL 16 — mesma instância, bancos dedicados por serviço" {

                uploadDb = container "arch_uploads" "Banco exclusivo do Upload Service. Tabelas: uploads (id UUID, filename, content_type, file_size, status, file_path, minio_url, created_at, updated_at) e users (autenticação JWT). Ciclo de vida do status: RECEIVED → PROCESSING → DONE | ERROR. Criado automaticamente pelo POSTGRES_DB na primeira inicialização do container." "PostgreSQL 16 :5432" {
                    tags "Database"
                }

                reportsDb = container "arch_reports" "Banco exclusivo do Report Service. Tabela: feedback (id SERIAL, upload_id UUID, rating INT 1–5, comment TEXT, created_at). Sem FK para uploads pois estão em bancos distintos. Criado de forma idempotente por initContainer create-db no boot do pod (Kubernetes) ou pelo serviço postgres-setup (Docker Compose)." "PostgreSQL 16 :5432" {
                    tags "Database"
                }
            }

            // ── Observabilidade ───────────────────────────────────────────────────────
            group "Observabilidade (Kubernetes: namespace arch-geral)" {

                prometheus = container "Prometheus" "Coleta métricas dos serviços via scrape HTTP de /metrics. No Kubernetes usa ClusterRole para auto-descoberta de pods via annotations (prometheus.io/scrape, prometheus.io/port, prometheus.io/path). Targets: upload-service (:8001), ai-service (:8003), report-service (:8004), RabbitMQ (:15692), postgres-exporter (:9187)." "Prometheus v2.52 :9090" {
                    tags "Monitoring"
                }

                grafana = container "Grafana" "Dashboards de métricas e logs. Datasources provisionados automaticamente: Prometheus (métricas HTTP) e Loki (logs estruturados). Dashboards: Arch Analyzer Overview e Arch Analyzer Logs. Autenticação configurada via GF_SECURITY_ADMIN_USER/PASSWORD." "Grafana 10.4 :3000" {
                    tags "Monitoring"
                }

                loki = container "Loki" "Armazenamento e indexação de logs estruturados (JSON) enviados pelo Promtail. Consultas via Grafana com LogQL. Configurado com armazenamento local em volume persistente." "Grafana Loki 2.9 :3100" {
                    tags "Monitoring"
                }

                promtail = container "Promtail" "Coleta logs dos containers e os encaminha para o Loki. No Docker Compose lê via socket Docker (/var/run/docker.sock). No Kubernetes lê os arquivos de log dos pods em /var/log/pods/ via DaemonSet." "Grafana Promtail 3.3" {
                    tags "Monitoring"
                }

                postgresExporter = container "postgres-exporter" "Exporta métricas internas do PostgreSQL (conexões ativas, transações, tamanho de bancos, locks) para o Prometheus via endpoint /metrics. Disponível somente no ambiente Docker Compose." "prometheuscommunity/postgres-exporter v0.13 :9187" {
                    tags "Monitoring"
                }
            }
        }

        // ─── Relacionamentos: Pessoa → Frontend ───────────────────────────────────────
        analista -> frontend "Faz upload de diagrama, acompanha status do processamento, lê o relatório de análise e envia feedback com nota" "HTTPS"

        // ─── Relacionamentos: Frontend → Serviços ────────────────────────────────────
        frontend -> uploadService "Proxy /upload-service/ — POST /upload, GET /uploads, GET /uploads/{id}, POST /token, GET /stats/uploads" "HTTP/REST + JWT"
        frontend -> aiService "Proxy /ai-service/ — GET /health, POST /analyze" "HTTP/REST"
        frontend -> reportService "Proxy /report-service/ — GET /reports, GET /reports/{id}, GET /reports/{id}/attachment, POST /feedback, GET /stats" "HTTP/REST + JWT"
        frontend -> rabbitmq "Proxy /infra-health/rabbitmq — verifica disponibilidade do management no painel" "HTTP"
        frontend -> grafana "Proxy /infra-health/grafana — verifica disponibilidade no painel" "HTTP"
        frontend -> prometheus "Proxy /infra-health/prometheus — verifica disponibilidade no painel" "HTTP"
        frontend -> loki "Proxy /infra-health/loki — verifica disponibilidade no painel" "HTTP"

        // ─── Relacionamentos: Upload Service ──────────────────────────────────────────
        uploadService -> uploadDb "INSERT/UPDATE/SELECT — tabelas uploads e users" "asyncpg TCP 5432"
        uploadService -> minio "PUT arquivo recebido do usuário (key: upload_id/filename)" "S3 API TCP 9000"
        uploadService -> rabbitmq "Publica → diagram.upload {upload_id, filename, file_path, content_type}" "AMQP TCP 5672"
        rabbitmq -> uploadService "Entrega ← diagram.result {upload_id, status, payload_json?, error_message?}" "AMQP TCP 5672"

        // ─── Relacionamentos: AI Service ──────────────────────────────────────────────
        rabbitmq -> aiService "Entrega ← diagram.upload {upload_id, filename, file_path, content_type}" "AMQP TCP 5672"
        aiService -> minio "GET arquivo para OCR e análise (usando file_path da mensagem)" "S3 API TCP 9000"
        aiService -> openRouter "POST OCR multimodal Gemma 4 26B + swarm de análise DeepSeek v3.2 via Strands" "HTTPS"
        aiService -> rabbitmq "Publica → diagram.result {upload_id, status: PROCESSING|DONE|ERROR, payload_json?}" "AMQP TCP 5672"

        // ─── Relacionamentos: Report Service ──────────────────────────────────────────
        reportService -> uploadService "GET /uploads/{id}, GET /uploads, GET /stats/uploads — JWT service-to-service (token obtido via POST /token com UPLOAD_SERVICE_USER/PASSWORD, renovado automaticamente 60s antes do vencimento)" "HTTP/REST + JWT"
        reportService -> reportsDb "INSERT feedback, SELECT AVG(rating) + COUNT(*) FROM feedback" "asyncpg TCP 5432"
        reportService -> minio "GET arquivo original para servir como attachment ao usuário" "S3 API TCP 9000"

        // ─── Relacionamentos: Observabilidade ─────────────────────────────────────────
        prometheus -> uploadService "Scrape GET /metrics (annotations: prometheus.io/scrape=true, porta 8001)" "HTTP"
        prometheus -> aiService "Scrape GET /metrics (annotations: prometheus.io/scrape=true, porta 8003)" "HTTP"
        prometheus -> reportService "Scrape GET /metrics (annotations: prometheus.io/scrape=true, porta 8004)" "HTTP"
        prometheus -> rabbitmq "Scrape GET /metrics (porta Prometheus: 15692)" "HTTP"
        prometheus -> postgresExporter "Scrape GET /metrics" "HTTP"
        postgresExporter -> uploadDb "Consulta métricas internas do PostgreSQL (ambos os bancos na mesma instância)" "TCP 5432"
        grafana -> prometheus "Datasource — consultas PromQL para dashboards de métricas" "HTTP"
        grafana -> loki "Datasource — consultas LogQL para dashboards de logs" "HTTP"
        promtail -> loki "Push de logs estruturados (JSON) dos containers" "HTTP"

        // ─── Relacionamentos: CI/CD ────────────────────────────────────────────────────
        github -> archAnalyzer "Build, testes e deploy contínuo. Push em main → arch-prod. Push em hmg → arch-hmg. Imagens no GHCR com tag branch-sha." "GitHub Actions + SSH + kubectl"

        // ─── Ambiente de Deploy: Docker Compose (Desenvolvimento Local) ───────────────
        deploymentEnvironment "Local" {
            deploymentNode "Docker Host" "Máquina de desenvolvimento (Linux, macOS ou WSL2)" "Docker Engine" {
                deploymentNode "arch-network" "Rede bridge interna. Todos os containers se comunicam por nome de serviço DNS" "Docker Bridge Network" {
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

        // ─── Ambiente de Deploy: Kubernetes na VPS (Produção / Homologação) ───────────
        deploymentEnvironment "Producao" {
            deploymentNode "VPS" "Servidor dedicado Ubuntu. Kind cluster com NodePorts mapeados para portas do host via socat. Nginx como reverse proxy com SSL (Let's Encrypt)." "Ubuntu Linux" {

                deploymentNode "Nginx Host" "Reverse proxy com TLS. Roteia: / → frontend NodePort (30080 prod / 30081 hmg), /rabbitmq/ → RabbitMQ management NodePort (30086 prod / 30087 hmg). Grafana e Prometheus expostos via socat em 30082 e 30084." "Nginx + certbot" {
                }

                deploymentNode "Kind Cluster" "Kubernetes in Docker. Cluster único com múltiplos namespaces para isolamento entre ambientes e camadas." "Kind (Kubernetes)" {

                    deploymentNode "arch-prod" "Namespace de produção (branch main) — ou arch-hmg para branch hmg. Recriado a cada push via GitHub Actions." "Kubernetes Namespace" {

                        deploymentNode "frontend" "" "Deployment (1 réplica)" {
                            containerInstance frontend
                        }

                        deploymentNode "upload-service" "initContainer create-db garante que arch_uploads existe antes do boot" "Deployment (1 réplica)" {
                            containerInstance uploadService
                        }

                        deploymentNode "ai-service" "ScaledObject KEDA: escala com base no tamanho da fila diagram.upload. Min: 1 réplica, Max: MAX_REPLICAS. Threshold: QUEUE_MESSAGES_PER_REPLICA mensagens/réplica. Cooldown: 60s." "Deployment (KEDA autoscaling)" {
                            containerInstance aiService
                        }

                        deploymentNode "report-service" "initContainer create-db garante que arch_reports existe antes do boot" "Deployment (1 réplica)" {
                            containerInstance reportService
                        }

                        deploymentNode "rabbitmq" "PVC rabbitmq-data: 5Gi. NodePort para management UI (30086/30087)" "StatefulSet (1 réplica)" {
                            containerInstance rabbitmq
                        }

                        deploymentNode "minio" "PVC minio-data: 20Gi. Imagem pinada (RELEASE.2024-07-31) para evitar quebras" "StatefulSet (1 réplica)" {
                            containerInstance minio
                        }

                        deploymentNode "postgres" "PVC postgres-data: 10Gi. Contém arch_uploads e arch_reports na mesma instância PostgreSQL. postgres-setup via initContainers nos pods dependentes." "StatefulSet (1 réplica)" {
                            containerInstance uploadDb
                            containerInstance reportsDb
                        }

                        deploymentNode "ExternalName Services" "Services do tipo ExternalName apontando para arch-geral.svc.cluster.local. Permitem que o Nginx e o frontend resolvam grafana, prometheus e loki pelo nome curto." "Kubernetes Services" {
                        }
                    }

                    deploymentNode "arch-geral" "Namespace compartilhado de observabilidade. Não é rotacionado com o deploy da aplicação — mantém histórico de métricas e logs entre deploys." "Kubernetes Namespace" {

                        deploymentNode "prometheus-pod" "ClusterRole para auto-descoberta de pods em todos os namespaces via annotations" "Deployment (1 réplica)" {
                            containerInstance prometheus
                        }

                        deploymentNode "grafana-pod" "PVC grafana-data para persistência dos dashboards" "Deployment (1 réplica)" {
                            containerInstance grafana
                        }

                        deploymentNode "loki-pod" "PVC loki-data para persistência dos logs" "Deployment (1 réplica)" {
                            containerInstance loki
                        }

                        deploymentNode "promtail-pod" "Lê /var/log/pods/ do nó. Monta hostPath para acesso aos logs de todos os pods do cluster" "DaemonSet" {
                            containerInstance promtail
                        }
                    }
                }
            }
        }
    }

    views {

        // ─── Nível 1: Contexto do Sistema ─────────────────────────────────────────────
        systemContext archAnalyzer "SystemContext" {
            title "Arch Analyzer — Contexto do Sistema (C4 Nível 1)"
            include *
            autoLayout tb
        }

        // ─── Nível 2: Containers ───────────────────────────────────────────────────────
        container archAnalyzer "Containers" {
            title "Arch Analyzer — Visão de Containers (C4 Nível 2)"
            include *
            autoLayout
        }

        // ─── Nível 3: Fluxo de Upload e Análise ───────────────────────────────────────
        dynamic archAnalyzer "UploadFlow" {
            title "Fluxo: Upload e Análise de Diagrama"

            analista -> frontend "1. Seleciona e envia arquivo (PNG/JPG/PDF)"
            frontend -> uploadService "2. POST /upload-service/upload (JWT)"
            uploadService -> minio "3. PUT arquivo no MinIO (key: upload_id/filename)"
            uploadService -> uploadDb "4. INSERT uploads — status = RECEIVED"
            uploadService -> rabbitmq "5. Publica diagram.upload {upload_id, filename, file_path, content_type}"
            rabbitmq -> aiService "6. Entrega diagram.upload (prefetch=1)"
            aiService -> rabbitmq "7. Publica diagram.result {upload_id, status: PROCESSING}"
            rabbitmq -> uploadService "8. Entrega diagram.result (PROCESSING)"
            uploadService -> uploadDb "9. UPDATE uploads SET status = PROCESSING"
            aiService -> minio "10. GET arquivo para OCR (usando file_path)"
            aiService -> openRouter "11. OCR multimodal Gemma 4 26B + swarm Strands DeepSeek v3.2"
            aiService -> rabbitmq "12. Publica diagram.result {upload_id, status: DONE, payload_json}"
            rabbitmq -> uploadService "13. Entrega diagram.result (DONE)"
            uploadService -> uploadDb "14. UPDATE status = DONE, file_path = payload_json (JSON com components, risks, summary)"

            autoLayout
        }

        // ─── Nível 3: Fluxo de Relatório e Feedback ───────────────────────────────────
        dynamic archAnalyzer "ReportFlow" {
            title "Fluxo: Consulta de Relatório e Envio de Feedback"

            analista -> frontend "1. Abre relatório de um upload"
            frontend -> reportService "2. GET /report-service/reports/{id} (JWT)"
            reportService -> uploadService "3. GET /uploads/{id} (JWT service-to-service)"
            uploadService -> uploadDb "4. SELECT * FROM uploads WHERE id = ?"
            uploadService -> reportService "5. UploadDetail {status, filename, file_path: payload_json, minio_url}"
            reportService -> frontend "6. ReportResponse {analysis, status, filename, minio_url}"

            analista -> frontend "7. Envia avaliação (nota 1–5 + comentário)"
            frontend -> reportService "8. POST /report-service/feedback {upload_id, rating, comment}"
            reportService -> uploadService "9. GET /uploads/{id} — verifica se o upload existe"
            reportService -> reportsDb "10. INSERT feedback (upload_id, rating, comment)"

            autoLayout
        }

        // ─── Nível 3: Fluxo de Estatísticas ───────────────────────────────────────────
        dynamic archAnalyzer "StatsFlow" {
            title "Fluxo: Estatísticas Combinadas de Dois Bancos"

            analista -> frontend "1. Acessa painel de estatísticas"
            frontend -> reportService "2. GET /report-service/stats"
            reportService -> uploadService "3. GET /stats/uploads (JWT service-to-service)"
            uploadService -> uploadDb "4. SELECT status, COUNT(*) FROM uploads GROUP BY status"
            uploadService -> reportService "5. {total: N, by_status: {RECEIVED: x, PROCESSING: y, DONE: z, ERROR: w}}"
            reportService -> reportsDb "6. SELECT AVG(rating)::NUMERIC(2,1), COUNT(*) FROM feedback"
            reportService -> frontend "7. Statistics {total_uploads, by_status, avg_rating, total_feedback}"

            autoLayout
        }

        // ─── Deploy: Docker Compose ────────────────────────────────────────────────────
        deployment archAnalyzer "Local" "LocalDeployment" {
            title "Deploy: Docker Compose — Desenvolvimento Local"
            include *
            autoLayout
        }

        // ─── Deploy: Kubernetes ────────────────────────────────────────────────────────
        deployment archAnalyzer "Producao" "KubernetesDeployment" {
            title "Deploy: Kubernetes na VPS (arch-prod / arch-hmg)"
            include *
            autoLayout
        }

        // ─── Estilos ───────────────────────────────────────────────────────────────────
        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
                fontSize 14
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "External System" {
                background #6b6b6b
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
                background #438dd5
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
                background #4A4A4A
                color #ffffff
            }
            relationship "Relationship" {
                fontSize 11
                color #707070
            }
        }
    }
}
