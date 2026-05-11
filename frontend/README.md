# Arch Analyzer — Frontend

SPA estática servida por **Nginx** na porta **8051**. O painel faz login no `upload-service`, obtém um JWT e chama as APIs dos microsserviços através do proxy na **mesma origem** (evita CORS e mantém o token só no browser).

## Estrutura

```
frontend/
├── index.html           # Shell da aplicação
├── script.js            # Lógica (auth, upload, dashboard, relatório)
├── styles.css           # Estilos
├── security-logger.js   # Hooks de logging (segurança)
├── fiap-png.png         # Asset
├── nginx.conf           # Proxy para upload / ai / report + CSP
├── Dockerfile           # Imagem nginx:alpine
└── README.md
```

## Quick start

### Local (só arquivos estáticos)

Sirva a pasta com um servidor HTTP qualquer **ou** use o stack completo via Docker Compose em `infrastructure/` (recomendado), para que `/upload-service`, `/ai-service` e `/report-service` existam como rotas proxy.

### Docker (imagem frontend)

```bash
cd frontend
docker build -t arch-analyzer-frontend .
docker run -p 8051:8051 arch-analyzer-frontend
```

Sem o Compose, o proxy do `nginx.conf` não terá os hostnames `upload-service`, `ai-service`, etc., então as chamadas à API falharão fora da rede do projeto.

## Variáveis

Esta camada **não** usa `BACKEND_URL`: as URLs são relativas ao host (ex.: `/upload-service/token`). O Compose sobe o frontend na mesma rede dos microsserviços e o Nginx encaminha para os serviços internos.

## API (via proxy, mesma origem)

Todas as rotas abaixo passam pelo Nginx em `8051`. Endpoints de negócio (exceto `/health` simples e login) exigem cabeçalho `Authorization: Bearer <jwt>` obtido em `POST /upload-service/token`.

| Método | Caminho (via proxy) | Descrição |
|--------|----------------------|-----------|
| POST | `/upload-service/token` | Login (form `username` / `password`) → JWT |
| POST | `/upload-service/upload` | Upload do diagrama |
| GET | `/upload-service/uploads` | Lista uploads |
| GET | `/upload-service/uploads/{id}` | Detalhe do upload |
| POST | `/ai-service/analyze` | Análise síncrona (texto já) |
| GET | `/report-service/reports` | Lista relatórios |
| GET | `/report-service/reports/{id}` | Detalhe do relatório |
| GET | `/report-service/reports/{id}/attachment` | Arquivo original (autenticado) |
| POST | `/report-service/feedback` | Feedback |
| GET | `/report-service/stats` | Estatísticas |
| GET | `/report-service/health` | Liveness (público) |
| GET | `/report-service/health/db` | **Ping ao Postgres (JWT obrigatório)** |
| GET | `/upload-service/health`, `/ai-service/health` | Liveness dos serviços |

Rotas antigas `/api/v1/...` **não** existem neste projeto; o cliente usa exclusivamente os prefixos acima.

## Integração com docker-compose

Ver `infrastructure/docker-compose.yml`: o serviço `frontend` publica `8051:8051` e depende dos microsserviços. Configure `JWT_SECRET_KEY`, `ADMIN_USER` e `ADMIN_PASSWORD` no `.env` da pasta `infrastructure`.
