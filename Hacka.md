# HACKATON

> Documento convertido a partir do PDF **HACKATON - 12SOAT + 6IADT (1)(3).pdf**.
>
> Observação: as páginas 1 e 8 são predominantemente visuais, com imagem de fundo e marca **Pós Tech**. O conteúdo textual principal começa na página 2.

---

# Hackathon Integrado - IA para Devs (IADT) + Software Architecture (SOAT)

## O problema

Empresas que operam sistemas distribuídos possuem dezenas de diagramas de arquitetura, geralmente armazenados como imagens ou PDFs, utilizados em:

- Revisões arquiteturais;
- Auditorias de segurança;
- Avaliações de escalabilidade;
- Discussões técnicas entre times.

Esses diagramas:

- São analisados manualmente;
- Demandam muito tempo;
- Dependem de especialistas;
- Não escalam.

A empresa fictícia **FIAP Secure Systems** decidiu criar um MVP de uma solução que permita enviar um diagrama de arquitetura de software e receber automaticamente uma análise técnica básica, com foco em componentes, riscos e recomendações arquiteturais.

## Objetivo

Construir um sistema back-end capaz de:

- Receber diagramas de arquitetura (imagem ou PDF);
- Processar esses diagramas;
- Aplicar IA para análise automática;
- Gerar um relatório técnico estruturado;
- Operar sobre uma arquitetura escalável e bem organizada.

---

## Escopo do MVP

O MVP deve cobrir um único fluxo principal, do início ao fim:

1. Upload de um diagrama de arquitetura.
2. Processamento do diagrama.
3. Análise automatizada.
4. Geração de relatório técnico.
5. Consulta do status do processamento.

---

## Organização dos grupos

Os grupos devem ser mistos, contendo alunos(as) dos dois cursos.

### Distribuição esperada de responsabilidades

#### Alunos(as) SOAT

Responsáveis por:

- Desenho da arquitetura do sistema;
- Definição dos microsserviços;
- Comunicação entre serviços;
- Persistência de dados;
- Infraestrutura;
- CI/CD;
- Observabilidade.

#### Alunos(as) IADT

Responsáveis por:

- Processamento do diagrama;
- Extração de informações com IA;
- Classificação ou análise automatizada;
- Geração do conteúdo do relatório;
- Avaliação básica da IA.

---

## Requisitos funcionais

Funcionalidades obrigatórias:

- Upload de diagrama (imagem ou PDF);
- Criação de um processo de análise;
- Consulta de status do processamento:
  - Recebido;
  - Em processamento;
  - Analisado;
  - Erro.
- Geração de relatório contendo:
  - Componentes identificados;
  - Possíveis riscos arquiteturais;
  - Recomendações básicas.

---

## Requisitos técnicos

### 1. Arquitetura de Software (SOAT)

- Arquitetura baseada em microsserviços;
- Comunicação via:
  - REST;
  - Ao menos um fluxo assíncrono (fila ou mensageria).
- Aplicação de:
  - Clean Architecture ou Arquitetura Hexagonal.
- Cada serviço deve:
  - Possuir responsabilidade clara;
  - Ter banco de dados próprio;
  - Ter testes automatizados.

#### Serviços mínimos sugeridos

- API Gateway ou BFF;
- Serviço de Upload e Orquestração;
- Serviço de Processamento;
- Serviço de Relatórios.

### 2. Inteligência Artificial (IADT)

A IA deve implementar ao menos uma das abordagens abaixo, considerando práticas de segurança, controle e avaliação do modelo:

- Detecção de componentes arquiteturais em imagens;
- Classificação de riscos arquiteturais a partir de regras + ML;
- Uso de LLM para geração de relatório técnico estruturado, com implementação de guardrails para controle de entrada, saída e mitigação de alucinações;
- Análise textual baseada em prompt engineering, incluindo validação de prompts, restrições de formato e avaliação da consistência das respostas.

#### Requisitos mínimos

- Pipeline claro de IA;
- Justificativa da abordagem escolhida;
- Demonstração prática da análise;
- Discussão de limitações do modelo.

### 3. Integração IA + Sistema

A IA deve ser parte do fluxo do sistema, e não um script isolado.

Deve ficar claro:

- Como a IA é acionada;
- Como o sistema trata falhas da IA;
- Como o resultado da IA é persistido;
- Como o relatório é gerado a partir da análise.

### 4. Infraestrutura e DevOps

Obrigatório:

- Docker;
- Docker Compose ou Kubernetes;
- Pipeline CI/CD contendo:
  - Build;
  - Testes;
  - Deploy (local ou cloud).

### 5. Qualidade e observabilidade

- Logs estruturados;
- Tratamento de erros;
- Testes unitários;
- README explicativo.

---

## Entregáveis

### 1. Código

Repositório Git contendo:

- Código-fonte;
- Dockerfile;
- `docker-compose` ou manifestos;
- Pipeline de CI/CD.

### 2. Documentação

README contendo:

- Descrição do problema;
- Arquitetura proposta;
- Fluxo da solução;
- Instruções de execução.

Também deve conter:

- Diagrama de arquitetura.

#### Seção obrigatória: Segurança

A documentação deve incluir uma seção obrigatória de segurança contendo:

- Descrição dos requisitos básicos de segurança adotados na solução;
- Estratégias de validação e tratamento de entradas não confiáveis;
- Uso controlado de modelos de IA, com definição de escopo e previsibilidade das respostas;
- Tratamento seguro de falhas ou comportamentos inesperados da IA;
- Práticas mínimas de segurança na comunicação entre serviços;
- Identificação e documentação dos principais riscos e limitações de segurança da solução.

### 3. Vídeo (até 15 minutos)

O vídeo deve demonstrar:

- Arquitetura da solução;
- Fluxo completo do sistema;
- Upload de um diagrama;
- Processamento e análise;
- Relatório gerado.
