workspace "Arch Analyzer" "Sistema de análise automática de diagramas de arquitetura com IA" {

    model {

        // ─── Pessoas ───────────────────────────────────────────────────────────────
        analista = person "Analista" "Faz upload de diagramas de arquitetura e consulta análises geradas pela IA"

        // ─── Sistema Principal ─────────────────────────────────────────────────────
        archAnalyzer = softwareSystem "Arch Analyzer" "Analisa diagramas de arquitetura via OCR + LLM e exibe relatórios estruturados com riscos e componentes identificados" {

            frontend = container "Frontend" "Interface web: upload de diagrama, listagem de uploads e visualização de relatórios de análise" "Streamlit :8051" {
                tags "Web Browser"
            }

            uploadService = container "Upload Service" "Recebe arquivos, persiste metadados no banco próprio, publica eventos de upload na fila e consome resultados da análise para atualizar o status" "FastAPI + Python :8001"

            aiService = container "AI Service" "Consome eventos de upload, executa OCR (extração de texto) e análise LLM, publica o resultado na fila. Sem acesso direto a banco de dados." "FastAPI + Python :8003"

            reportService = container "Report Service" "Serve relatórios e coleta feedback. Lê dados de uploads via HTTP do Upload Service e persiste feedback no banco próprio." "FastAPI + Python :8004"

            rabbitmq = container "RabbitMQ" "Broker de mensagens assíncronas. Fila diagram.upload (upload → ai-service). Fila diagram.result (ai-service → upload-service)." "RabbitMQ 3.13" {
                tags "Message Broker"
            }

            minio = container "MinIO" "Armazenamento de objetos para os arquivos de diagrama enviados pelos usuários" "MinIO S3-compatible" {
                tags "File System"
            }

            group "PostgreSQL — mesma instância, bancos dedicados por serviço" {

                uploadDb = container "arch_uploads" "Banco dedicado ao Upload Service. Dono exclusivo da tabela uploads (id, filename, status, file_path, minio_url)." "PostgreSQL 16" {
                    tags "Database"
                }

                reportsDb = container "arch_reports" "Banco dedicado ao Report Service. Dono exclusivo da tabela feedback (upload_id, rating, comment)." "PostgreSQL 16" {
                    tags "Database"
                }
            }
        }

        // ─── Sistemas Externos ─────────────────────────────────────────────────────
        openrouter = softwareSystem "OpenRouter / LLM" "API externa de modelos de linguagem: análise de diagramas (DeepSeek v3) e OCR multimodal (Gemma)" {
            tags "External System"
        }

        // ─── Relacionamentos ───────────────────────────────────────────────────────

        // Pessoa → Frontend
        analista -> frontend "Faz upload, consulta relatórios e envia feedback" "HTTPS"

        // Frontend → Serviços (HTTP autenticado via JWT)
        frontend -> uploadService "POST /upload, GET /uploads, GET /uploads/{id}, POST /token" "HTTP/REST + JWT"
        frontend -> reportService "GET /reports/{id}, GET /reports, POST /feedback, GET /stats" "HTTP/REST + JWT"

        // Serviço → Serviço (HTTP interno)
        reportService -> uploadService "GET /uploads/{id}, GET /uploads, GET /stats/uploads" "HTTP/REST + JWT service-to-service"

        // Upload Service → dependências
        uploadService -> uploadDb "INSERT/UPDATE/SELECT — tabela uploads" "asyncpg TCP 5432"
        uploadService -> minio "PUT arquivo enviado pelo usuário" "S3 API"
        uploadService -> rabbitmq "Publica → diagram.upload {upload_id, file_path}" "AMQP"
        rabbitmq -> uploadService "Entrega ← diagram.result {status, payload_json}" "AMQP"

        // AI Service → dependências
        rabbitmq -> aiService "Entrega ← diagram.upload {upload_id, file_path}" "AMQP"
        aiService -> minio "GET arquivo para análise OCR" "S3 API"
        aiService -> openrouter "POST análise LLM + OCR multimodal" "HTTPS"
        aiService -> rabbitmq "Publica → diagram.result {status, payload_json}" "AMQP"

        // Report Service → dependências
        reportService -> reportsDb "INSERT/SELECT — tabela feedback" "asyncpg TCP 5432"
        reportService -> minio "GET arquivo original para download" "S3 API"
    }

    views {

        // ─── Nível 1: Contexto do Sistema ─────────────────────────────────────────
        systemContext archAnalyzer "SystemContext" {
            title "Arch Analyzer — Contexto do Sistema (C4 Nível 1)"
            include *
            autoLayout tb
        }

        // ─── Nível 2: Containers ───────────────────────────────────────────────────
        container archAnalyzer "Containers" {
            title "Arch Analyzer — Visão de Containers (C4 Nível 2)"
            include *
            autoLayout
        }

        // ─── Nível 3: Sequência — Fluxo de Upload e Análise ───────────────────────
        dynamic archAnalyzer "UploadFlow" {
            title "Fluxo: Upload e Análise de Diagrama"

            analista -> frontend "1. Seleciona e envia arquivo"
            frontend -> uploadService "2. POST /upload (JWT)"
            uploadService -> minio "3. PUT arquivo no MinIO"
            uploadService -> uploadDb "4. INSERT uploads — status = RECEIVED"
            uploadService -> rabbitmq "5. Publica diagram.upload {upload_id, file_path}"
            rabbitmq -> aiService "6. Entrega diagram.upload"
            aiService -> minio "7. GET arquivo para análise"
            aiService -> rabbitmq "8. Publica diagram.result {status: PROCESSING}"
            rabbitmq -> uploadService "9. Entrega diagram.result (PROCESSING)"
            uploadService -> uploadDb "10. UPDATE status = PROCESSING"
            aiService -> openrouter "11. POST análise LLM + OCR"
            aiService -> rabbitmq "12. Publica diagram.result {status: DONE, payload_json}"
            rabbitmq -> uploadService "13. Entrega diagram.result (DONE)"
            uploadService -> uploadDb "14. UPDATE status = DONE, file_path = payload_json"

            autoLayout
        }

        // ─── Nível 3: Sequência — Consulta de Relatório e Feedback ───────────────
        dynamic archAnalyzer "ReportFlow" {
            title "Fluxo: Consulta de Relatório e Envio de Feedback"

            analista -> frontend "1. Abre relatório"
            frontend -> reportService "2. GET /reports/{id} (JWT)"
            reportService -> uploadService "3. GET /uploads/{id} (JWT service-to-service)"
            uploadService -> uploadDb "4. SELECT uploads WHERE id = ..."
            uploadService -> reportService "5. UploadDetail {status, file_path: payload_json, minio_url}"
            reportService -> frontend "6. ReportResponse {analysis, status, filename}"

            analista -> frontend "7. Envia feedback (nota + comentário)"
            frontend -> reportService "8. POST /feedback {upload_id, rating, comment}"
            reportService -> uploadService "9. GET /uploads/{id} — verifica existência"
            reportService -> reportsDb "10. INSERT feedback (upload_id, rating, comment)"

            autoLayout
        }

        // ─── Nível 3: Sequência — Estatísticas (dois bancos) ─────────────────────
        dynamic archAnalyzer "StatsFlow" {
            title "Fluxo: Estatísticas Combinadas de Dois Bancos"

            analista -> frontend "1. Acessa painel de estatísticas"
            frontend -> reportService "2. GET /stats"
            reportService -> uploadService "3. GET /stats/uploads"
            uploadService -> uploadDb "4. SELECT COUNT(*), status FROM uploads GROUP BY status"
            uploadService -> reportService "5. {total_uploads: N, by_status: {...}}"
            reportService -> reportsDb "6. SELECT AVG(rating), COUNT(*) FROM feedback"
            reportService -> frontend "7. Statistics {total_uploads, by_status, avg_rating, total_feedback}"

            autoLayout
        }

        // ─── Estilos ───────────────────────────────────────────────────────────────
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
                background #438dd5
                color #ffffff
            }
            element "Message Broker" {
                shape Pipe
                background #c04000
                color #ffffff
            }
            element "Database" {
                shape Cylinder
                background #2e6da4
                color #ffffff
            }
            element "File System" {
                shape Folder
                background #438dd5
                color #ffffff
            }
            relationship "Relationship" {
                fontSize 11
                color #707070
            }
        }
    }
}
