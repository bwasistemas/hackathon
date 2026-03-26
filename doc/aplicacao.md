# Visão geral da aplicação

## Propósito

O **Arch Analyzer** é um sistema distribuído que recebe diagramas de arquitetura (imagens ou PDF), extrai texto por OCR quando necessário, envia o conteúdo a um modelo de linguagem (LLM) e devolve uma análise estruturada: componentes identificados, riscos arquiteturais e um resumo. O cenário típico é um hackathon ou laboratório acadêmico, com foco em desacoplamento entre serviços e observabilidade.

## Arquitetura em alto nível

O sistema segue um padrão de **microsserviços** orquestrados por Docker Compose:

- **Frontend** (interface web estática servida por Nginx) expõe o painel e o fluxo de upload.
- **Upload Service** recebe arquivos, persiste metadados no PostgreSQL e publica mensagens na fila **RabbitMQ**.
- **AI Service** consome a fila, executa OCR (Tesseract, PDF via Poppler), chama a API do provedor LLM e atualiza o registro do upload no banco.
- **Report Service** consulta o PostgreSQL e expõe APIs para listar e servir análises já persistidas (sem chamar LLM nem ler arquivos de upload diretamente no fluxo principal de leitura).
- **PostgreSQL** centraliza o estado dos uploads e o payload da análise.
- **Prometheus** e **Grafana** coletam e exibem métricas HTTP dos serviços FastAPI.

Um diagrama textual da arquitetura e a lista de portas estão no [`README.md`](../README.md) na raiz do repositório.

## Fluxo principal (resumo)

1. O usuário envia um diagrama pelo frontend para o **Upload Service**.
2. O serviço grava o arquivo (volume compartilhado), cria ou atualiza a linha na tabela de uploads (por exemplo status `RECEIVED`) e publica uma mensagem na fila (por exemplo `diagram.upload`) com identificador do upload e caminho do arquivo.
3. O **AI Service** processa a mensagem em background: marca o upload como em processamento, extrai texto (imagem ou PDF), chama o LLM com um prompt fixo que exige resposta em JSON e, ao final, marca o upload como concluído e grava o resultado (texto + saída da IA) no banco.
4. O **Report Service** e/ou o frontend consumem as APIs de relatório para exibir componentes, riscos e resumo no painel.

## Serviços e portas (referência)

| Serviço | Porta | Função resumida |
|---------|-------|-----------------|
| Frontend | 8051 | Interface web |
| Upload API | 8001 | Upload e registro de diagramas |
| AI API | 8003 | Health, endpoint `/analyze` (teste direto) e worker RabbitMQ + OCR + LLM |
| Report API | 8004 | Leitura de análises do banco |
| RabbitMQ | 5672 / 15672 | Fila AMQP e interface de gestão |
| PostgreSQL | 5432 | Persistência |
| Prometheus | 9090 | Métricas |
| Grafana | 3000 | Dashboards |

Valores exatos de URL e credenciais padrão de desenvolvimento aparecem no `README.md` principal.

## Configuração

As variáveis de ambiente são definidas principalmente em `infrastructure/.env` (a partir de `infrastructure/.env.example`). Pontos importantes:

- **PostgreSQL**: usuário, senha e nome do banco.
- **RabbitMQ**: host, porta, usuário e senha (o AI Service usa esses valores para conectar e consumir a fila).
- **LLM**: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (compatível com OpenAI ou proxies como OpenRouter) e `LLM_MODEL`.

Em produção, altere senhas padrão e evite expor o PostgreSQL publicamente.

## Como executar

Formas comuns:

- **Script `./setup.sh`** na raiz do repositório: verifica Docker, cria `.env` se faltar, faz build e sobe os containers.
- **Docker Compose manual**: `cd infrastructure && docker compose up -d` (ou `docker-compose`, conforme ambiente).

O frontend pode ser servido localmente para desenvolvimento (por exemplo `python -m http.server` na pasta do frontend), conforme descrito no README.

## Observabilidade

Os serviços FastAPI expõem métricas compatíveis com Prometheus (por exemplo via instrumentação HTTP). O Grafana pode ser provisionado com dashboards que apontam para o Prometheus como fonte de dados.

## CI/CD

O repositório inclui pipeline de CI (por exemplo lint, testes e build de imagens). Detalhes específicos estão em `infrastructure/.github/workflows/`.

## Onde aprofundar

- Detalhes internos do **AI Service** (camadas hexagonais, portas e adaptadores): [ai-service.md](ai-service.md).
