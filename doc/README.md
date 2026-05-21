# Documentação — Arch Analyzer

Documentação em português do sistema **Arch Analyzer**: análise automatizada de diagramas de arquitetura de software.

## Conteúdo

| Documento | Descrição |
|-----------|-----------|
| [Visão geral da aplicação](aplicacao.md) | Propósito, arquitetura de microsserviços, fluxos, portas, configuração e execução |
| [Upload Service — arquitetura hexagonal](upload-service.md) | Recepção de arquivos, JWT, filas RabbitMQ, adaptadores asyncpg/MinIO e ciclo de vida de status |
| [AI Service — arquitetura hexagonal](ai-service.md) | OCR multimodal, swarm Strands/DeepSeek, portas e adaptadores do serviço de IA |
| [Report Service — arquitetura hexagonal](report-service.md) | Relatórios via HTTP s2s, feedback, estatísticas e adaptador HttpUploadClientAdapter |

## Referências rápidas

- Documentação principal do repositório: [`../README.md`](../README.md)
- Infraestrutura Docker e observabilidade: [`../infrastructure/README.md`](../infrastructure/README.md)
