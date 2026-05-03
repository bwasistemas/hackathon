# Pontos para melhoria da aplicação

## Infraestrutura
- [ ] Utilizar Docker e/ou Kubernets
- [ ] Criar pipeline CI/CD com: build, testes e deploy.
- [ ] Utilizar [grafana loki](https://grafana.com/oss/loki/) para logs estruturados

## Arquitetura do Sistema

- [x] Desenhar a arquitetura do sistema
- [x] Definir arquitetura de cada microsserviço (clean ou hexagonal)
- [x] Revisar arquitetura para analisar a necessidade de novos microsserviços
- [x] Revisar comunicação entre o serviço de AI com a postgres, cada microsserviço deve ter sem BD próprio. Uma sugestão é publicar a mensagem no rabbit com o payload do que deve ser tratado, para evitar a comunicação do serviço de AI com o postgres e manter a separação
- [X] Subir ambiente do minio para integrar nos serviços
- [X] Atualizar código para  usar o blob storage, para armazenar os arquivos dos diagramas enviados. 
- [ ] Criar testes automatizados (unitários)
- [ ] Analisar a necessidade de utilizar um API gateway 

## Upload de arquivos

## Serviço de AI
- [X] Usar langgraph ou [sdk da aws](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/)
- [X] Utilizar multi agentes com o [sdk da aws](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/) ou [langgraph aws](https://reference.langchain.com/python/langgraph-swarm)
- [X] Usar baratinha para fazer OCR e um modelo mais robusto para analisar e gerar a sugestão da arquitetura
- [ ] Refinar prompts da aplicação
- [X] Adicionar guardrails
- [ ] Aplicar técnicas de antialucinação
- [ ] Criar relatório com os seguintes pontos: Justificativa da abordagem escolhida;  Demonstração prática da análise; Discussão de limitações do modelo; Como a IA é acionada; Como o sistema trata falhas da IA; Como o resultado da IA é persistido; Como o relatório é gerado a partir da análise;

## Segurança
- [ ] Descrição dos requisitos básicos de segurança adotados na solução

## Relátório

README contendo:

- Descrição do problema;
- Arquitetura proposta;
- Fluxo da solução;
- Instruções de execução.
  - Diagrama de arquitetura.
  - Seção obrigatória: Segurança
- Descrição dos requisitos básicos de segurança adotados na solução;
- Estratégias de validação e tratamento de entradas não confiáveis;
- Uso controlado de modelos de IA, com definição de escopo e
previsibilidade das respostas;
- Tratamento seguro de falhas ou comportamentos inesperados da IA;
- Práticas mínimas de segurança na comunicação entre serviços;
- Identificação e documentação dos principais riscos e limitações de
segurança da solução.
