# Atlas Investment OS — Auditoria do Estado Atual

**Data da auditoria:** 12 de julho de 2026  
**Código analisado:** `Atlas_Investment_OS(1).zip`  
**Versão declarada:** `1.0.0`  
**Último commit:** `b2b445e — PR-017.6: Remove dead pre-scoring Confidence Score + orphaned pipeline runner`

## 1. Resumo executivo

O Atlas está tecnicamente estável, modular e com uma suíte de regressão relevante. A versão 1.0.0 foi registrada no Git e os módulos de Portfolio Intelligence foram implementados e amplamente testados.

Entretanto, o produto executável principal (`run_all.py`) ainda opera essencialmente como a plataforma v0.9 de análise individual de empresas. Os módulos de Portfolio Intelligence existem no domínio e nos testes, mas não estão conectados ao fluxo principal, ao Excel padrão ou ao Morning Brief padrão.

Portanto, o estado correto é:

- **Core de análise de empresas:** operacional e integrado.
- **Decision Intelligence:** operacional e integrado.
- **Portfolio Intelligence:** implementado como domínio, mas ainda não integrado ao entrypoint principal.
- **Outcome Analytics:** não implementado.
- **Dashboard/API:** apenas estrutura inicial ou roadmap.
- **Documentação de release:** parcialmente desatualizada.

## 2. Evidências de estabilidade

### Testes

Execução local realizada no código extraído:

- **182 testes aprovados**
- **0 falhas**
- Tempo aproximado: **1,6 segundos** sem cobertura

### Cobertura

Cobertura global medida:

- **3.031 statements**
- **778 não cobertos**
- **74% de cobertura total**

Áreas fortes:

- `analytics/fundamentals.py`: 100%
- `analytics/mapper.py`: 100%
- `decision/engine.py`: 97%
- `decision/policy.py`: 98%
- `decision/thesis.py`: 99%
- `scoring/investment.py`: 98%
- Portfolio: geralmente entre 90% e 97%
- Reporting domain models: acima de 90%

Áreas sem cobertura ou com cobertura baixa:

- `analytics/feature_engine.py`: 0%
- `analytics/indicators.py`: 0%
- `database/atlas_db.py`: 0%
- `health/health_check.py`: 0%
- `metrics/execution.py`: 0%
- módulos antigos de scoring por fator: 0%
- `reports/explainability.py`: 46%
- `reports/morning_brief.py`: 58%

## 3. Fluxo executável atual

O entrypoint oficial é `run_all.py`.

Fluxo observado:

1. Executa Health Check.
2. Carrega `config/settings.json`.
3. Carrega `config/watchlist.csv`.
4. Consulta dados pelo provider Yahoo.
5. Enriquece cada ativo com indicadores técnicos.
6. Calcula fundamentos derivados.
7. Normaliza as colunas.
8. Executa o Investment Scoring.
9. Audita cobertura das features e pesos fantasmas.
10. Salva snapshot no SQLite.
11. Gera Excel histórico e `latest.xlsx`.
12. Gera `morning_brief.md`.
13. Exibe resumo no console.
14. Salva métricas de execução.

Representação simplificada:

```text
watchlist.csv
    ↓
Yahoo provider
    ↓
Technicals + Fundamentals
    ↓
Column Mapper
    ↓
Investment / Opportunity / Conviction / Decision
    ↓
Feature Coverage Audit
    ↓
SQLite History
    ↓
Excel + Morning Brief + Console + Execution Metrics
```

## 4. Estado por módulo

| Camada | Estado | Integração no `run_all.py` | Observação |
|---|---|---:|---|
| Providers / Yahoo | Operacional | Sim | Fonte externa principal |
| Analytics / Technicals | Operacional | Sim | Sem testes diretos |
| Analytics / Fundamentals | Operacional | Sim | Cobertura de 100% |
| Mapper | Operacional | Sim | Contratos recentes corrigidos |
| Feature Coverage Audit | Operacional | Sim | Detecta peso fantasma |
| Factor Engine | Operacional | Indireta/parcial | Há coexistência de motores antigos e novos |
| Investment Scoring | Operacional | Sim | Núcleo de scoring integrado |
| Opportunity Model | Operacional | Sim | Testado |
| Conviction Model | Operacional | Sim | Testado |
| Decision Policy | Operacional | Sim | Testado |
| Decision Engine | Operacional | Sim | Testado |
| Investment Thesis | Operacional | Sim, via relatórios | Testado |
| Historical Intelligence | Operacional | Sim | SQLite em `data/atlas_history.db` |
| Alerts | Operacional | Via relatórios | Boa cobertura |
| Excel Reports | Operacional | Sim | Gera latest e histórico |
| Morning Brief | Operacional | Sim | Arquivo grande, cobertura parcial |
| Health Check | Operacional | Sim | Sem cobertura automatizada |
| Execution Metrics | Operacional | Sim | Sem cobertura automatizada |
| Portfolio Loader / Models | Implementado | Não | Domínio maduro e testado |
| Portfolio Allocation | Implementado | Não | Cobertura de 96% |
| Portfolio Concentration | Implementado | Não | Cobertura de 95% |
| Portfolio Quality | Implementado | Não | Cobertura de 90% |
| Portfolio Rebalance | Implementado | Não | Advisory only, cobertura de 94% |
| Portfolio Report | Implementado | Não | Cobertura de 93% |
| Outcome Analytics | Não implementado | Não | Roadmap v1.1 antigo |
| Dashboard | Estrutura vazia | Não | Apenas pacote `dashboard` |
| REST API / Scheduler / Notifications | Não implementado | Não | Roadmap v2.0 |

## 5. Portfolio Intelligence

A camada de portfólio já contém:

- importação e validação de CSV;
- modelos `Holding` e `Portfolio`;
- métricas de alocação;
- concentração por posição e agrupamentos;
- qualidade do portfólio;
- ranking de posições;
- sugestões de rebalanceamento;
- tratamento de caixa como ativo;
- relatório de portfólio;
- suíte de testes ampla;
- ADRs e critérios de aceitação.

### Lacuna principal

Não há chamada dos módulos `portfolio.*` no `run_all.py`, nem referência a portfólio no fluxo padrão de Excel e Morning Brief.

Assim, Portfolio Intelligence está **implementado, mas não entregue como experiência operacional única**.

## 6. Configuração e fontes da verdade

Arquivos principais:

- `config/settings.json`: caminhos e período de histórico.
- `config/watchlist.csv`: universo monitorado.
- `config/features.yaml`: definição oficial das features.
- `config/model.yaml`: pesos dos fatores.
- `config/weights.json`: pesos utilizados pelo scoring integrado.
- `config/deal_breakers.json`: regras de exclusão e penalidade.
- `config/portfolio.example.csv`: modelo de entrada de portfólio.

### Risco de configuração duplicada

Há mais de uma representação de pesos/modelo (`features.yaml`, `model.yaml`, `weights.json`) e coexistem engines antigos e novos. O PR-017.3 tornou `features.yaml` autoritativo para valuation, mas a governança completa das fontes de verdade ainda precisa ser explicitada.

## 7. Git e integridade do ZIP

O `git status` mostra aproximadamente 142 arquivos modificados, com estatística simétrica de inserções e remoções.

A inspeção do diff confirma que a causa é conversão de finais de linha:

- versão registrada no Git: LF;
- arquivos do ZIP: CRLF.

Não há evidência, nessa diferença massiva, de alterações lógicas reais.

### Consequência

Não se deve criar um commit com o estado atual sem antes normalizar os line endings, pois isso produziria um commit enorme e esconderia mudanças reais.

### Ação recomendada

- definir política em `.gitattributes`;
- restaurar/renormalizar o working tree;
- confirmar `git status` limpo;
- somente depois iniciar nova evolução.

## 8. Inconsistências documentais

### Versão

- `VERSION`: `1.0.0`
- Git tag/commit de release: v1.0.0
- `README.md`: ainda declara `v0.9.0`

### Roadmap

`docs/ROADMAP.md` ainda apresenta Portfolio Intelligence como “Planned”, apesar dos módulos e testes já existirem.

### Backlog

`docs/BACKLOG.md` ainda marca todo o milestone de portfólio como pendente.

### Modelo

`config/model.yaml` contém comentário “Atlas default model v0.3”, que pode ser versão do modelo, mas precisa ser distinguida claramente da versão do produto.

## 9. Riscos técnicos priorizados

### P0 — Higiene do repositório

A conversão LF/CRLF contamina o Git e impede identificar alterações reais com segurança.

### P0 — Versão operacional incompleta

O produto se declara v1.0.0, mas o entrypoint não entrega a funcionalidade central da v1.0: Portfolio Intelligence.

### P1 — Documentação divergente

README, Roadmap e Backlog não representam o código atual.

### P1 — Cobertura ausente em componentes operacionais

Health Check, métricas, indicadores técnicos e banco alternativo não têm testes diretos.

### P1 — Dois bancos/persistências

Existem `database/atlas_db.py` e `storage/history_db.py`. É necessário documentar responsabilidades e decidir se ambos permanecem.

### P1 — Código legado/coexistente

Existem módulos antigos e novos para feature/scoring. A ausência de testes em vários módulos sugere código legado ou caminhos não utilizados.

### P2 — Morning Brief monolítico

`reports/morning_brief.py` possui grande volume de código e cobertura de 58%, elevando risco de regressão em mudanças futuras.

### P2 — Dependência exclusiva do Yahoo

Não há provider alternativo nem estratégia explícita de fallback para indisponibilidade, limites ou mudanças no payload.

## 10. Backlog recomendado para a próxima evolução

### PR-018.0 — Baseline limpo e documentação sincronizada

Objetivo: criar uma base confiável antes de alterar comportamento.

Entregas:

1. Adicionar `.gitattributes` com política de line endings.
2. Renormalizar o repositório.
3. Confirmar working tree limpo.
4. Atualizar README para v1.0.0.
5. Atualizar Roadmap e Backlog conforme o que já foi entregue.
6. Criar `docs/CURRENT_STATUS.md` como fonte única do estado atual.
7. Registrar o resultado dos 182 testes.

Critério de aceite:

- `git status` limpo;
- 182 testes aprovados;
- documentação sem divergência de versão.

### PR-018.1 — Portfolio Pipeline

Objetivo: conectar o domínio de portfólio ao produto executável.

Entregas:

1. Adicionar caminho do portfólio em `settings.json`.
2. Carregar CSV de portfólio de forma opcional.
3. Cruzar holdings com `CompanyReport`/resultado do scoring.
4. Calcular allocation, concentration, quality e rebalance.
5. Não quebrar execução quando não houver portfolio CSV.
6. Adicionar testes de integração do pipeline.

### PR-018.2 — Portfolio Excel

Objetivo: incluir visão do portfólio no `latest.xlsx`.

Sugestão de abas:

- Portfolio Summary
- Holdings
- Allocation
- Concentration
- Quality
- Rebalance Suggestions
- Data Warnings

### PR-018.3 — Portfolio Morning Brief

Objetivo: gerar uma seção executiva do portfólio.

Conteúdo mínimo:

- valor total e caixa;
- maiores posições;
- violações de concentração;
- qualidade média ponderada;
- posições incompatíveis com a decisão atual;
- sugestões de rebalanceamento advisory only.

### PR-018.4 — Testes dos componentes operacionais

Objetivo: elevar a cobertura sem testar código morto.

Prioridades:

1. `analytics/indicators.py`
2. `health/health_check.py`
3. `metrics/execution.py`
4. fluxo principal de `run_all.py`
5. integração do provider com fixtures/mocks
6. caminhos não cobertos do Morning Brief

Meta inicial recomendada: **80% global**, preservando qualidade dos testes.

### PR-018.5 — Consolidação de código e persistência

Objetivo: remover ambiguidades arquiteturais.

Entregas:

- mapear módulos realmente importados;
- descontinuar ou arquivar engines antigos;
- esclarecer `atlas_db` versus `history_db`;
- documentar a fonte oficial de pesos e features;
- adicionar testes contratuais de configuração.

### PR-019 — Outcome Analytics

Após a v1.0 estar integrada operacionalmente:

- registrar decisões e data da decisão;
- medir retorno futuro por janela;
- hit rate;
- calibração de Opportunity e Conviction;
- análise de regras e deal breakers;
- comparação decisão versus benchmark.

## 11. Sequência recomendada

```text
PR-018.0  Baseline / Git / documentação
    ↓
PR-018.1  Portfolio Pipeline
    ↓
PR-018.2  Portfolio Excel
    ↓
PR-018.3  Portfolio Morning Brief
    ↓
PR-018.4  Cobertura operacional
    ↓
PR-018.5  Consolidação arquitetural
    ↓
PR-019    Outcome Analytics
```

## 12. Conclusão

O Atlas não precisa de uma reconstrução. O núcleo está consistente, os testes passam e a arquitetura de portfólio já foi criada com boa cobertura.

A prioridade correta é transformar o código existente em uma release 1.0 operacionalmente coerente:

1. limpar o baseline Git;
2. sincronizar documentação;
3. integrar Portfolio Intelligence ao pipeline;
4. só então avançar para Outcome Analytics.

**Próximo passo recomendado:** executar o **PR-018.0 — Baseline limpo e documentação sincronizada**.
