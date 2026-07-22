# ADR-037 — PE ausente por prejuízo é estrutural (não-aplicável), EV/EBITDA ganha peso, e ROE ausente reconcilia via Finnhub (ou fica não-aplicável em patrimônio negativo)

- **Status**: Accepted
- **Data**: 2026-07-21
- **Relacionado**: ADR-012 (referência oficial de scoring), ADR-013 (separação cobertura/confiança/qualidade/frescor), `factors/engine.py::metric_has_value`/`metric_applicable`, `config/sell_rules.yaml::confidence_gate`

## Contexto

Rodando a carteira real (`--portfolio`) contra as 18 posições — com as teses já
preenchidas, portanto com o motor de venda destravado — **12 de 18 posições
travavam em `REVISAR`** pelo gate de confiança (`score_coverage ≥ 60` **e**
`confidence ≥ 60`, `config/sell_rules.yaml`). A causa dominante, medida no
snapshot de 2026-07-21, foi **PE (feature `required`) marcado como `missing`**
em 7 nomes: FMC, IBRX, BNTX, SGML, CLF, AVAV, YPF.

Investigação measure-first (evidência por campo, `field_evidence_json` do
snapshot) mostrou que **esses 7 nomes têm `ev_ebitda=present` e
`forward_pe=present`** — só falta o **PE trailing**, que o Yahoo omite porque a
empresa teve **lucro trailing não-positivo** (a razão é matematicamente
indefinida, não é falha de coleta). São nomes cíclicos/turnaround/pré-receita
(siderurgia, lítio, biotech, defesa em integração, energia argentina) com
valuation perfeitamente observável por outros múltiplos.

Tratar essa ausência estrutural como `missing` disparava o teto de
`Model Confidence` em 59 (`confidence.missing_required_cap`), um ponto abaixo do
gate de 60 — condenando metade da carteira a `REVISAR` permanente, sem nunca
produzir uma decisão real de compra/venda.

## Decisão

Duas mudanças, autorizadas pelo usuário como calibração consciente do modelo:

1. **PE ausente por prejuízo = `not_applicable`, não `missing`.**
   `providers/yahoo.py::_trailing_pe_structurally_absent` classifica a ausência
   de `trailingPE` como estrutural **somente quando há sinal positivo de lucro
   não-positivo** (`trailingEps ≤ 0`, `netIncomeToCommon ≤ 0` ou
   `profitMargins ≤ 0`). Nesse caso o campo `pe` entra em `not_applicable_fields`
   de `ensure_field_evidence`, recebendo status `NOT_APPLICABLE`.

   O motor **já tratava `NOT_APPLICABLE` corretamente** (nenhuma mudança em
   `factors/engine.py`): `metric_applicable` exclui a feature do denominador de
   cobertura (`score_valuation`/`score_factor` normalizam por `applicable_weight`)
   e o laço de `Missing Required Features` só acusa quando `applies and not
   present`. O bug era exclusivamente a **classificação na origem**.

   **Conservadorismo preservado**: PE ausente **sem nenhum sinal de earnings**
   permanece `missing` — uma falha genuína de coleta nunca é mascarada como
   estrutural. Coberto por `tests/test_yahoo_provider_contract.py::
   test_trailing_pe_marked_not_applicable_when_earnings_non_positive`.

2. **EV/EBITDA passa a ser o múltiplo de valuation dominante.**
   No bloco `valuation` de `config/features.yaml` (e no fallback espelhado
   `factors/valuation.py::VALUATION_FEATURES`, travado por
   `tests/test_valuation_config.py`), o peso migra de PE → EV/EBITDA:
   `pe: 0.20 → 0.10`, `ev_ebitda: 0.20 → 0.30` (soma do bloco preservada em 1.0,
   invariante travada por `tests/test_governed_config.py`). Racional: quando PE é
   frequentemente indefinido (empresas deficitárias) e o fator renormaliza pelos
   pesos aplicáveis, EV/EBITDA — imune ao sinal de lucro líquido — é o
   substituto natural para carregar o julgamento de valuation.

## Consequências

- Nomes deficitários com valuation completo deixam de travar no gate de
  confiança por um motivo espúrio; passam a receber decisão real do motor de
  compra/venda. (Prova ao vivo registrada na rodada `--portfolio` de 2026-07-21.)
- PE genuinamente ausente por falha de fetch continua penalizando confiança
  (comportamento conservador intacto).
- A mudança de peso altera o Investment Score de todo o universo (EV/EBITDA agora
  pesa 3× o PE dentro de valuation) — mudança de modelo deliberada, não silenciosa.
- `data_quality.yaml`/percentil por setor inalterados; a decisão é sobre
  **classificação de ausência** e **peso relativo**, não sobre fórmula de métrica.

## Adendo (mesma sessão) — ROE ausente: JNJ vs. IBRX exigem tratamento oposto

Investigando por que `roe` também travava JNJ e IBRX (`required: true` em
`config/features.yaml::business`), medi os dois casos ao vivo e achei que **não
são o mesmo problema**, apesar de ambos aparecerem como `roe=missing` no
snapshot:

- **JNJ**: `info.get("returnOnEquity")` vem `None` do Yahoo (gap de coleta —
  a chave simplesmente não veio nesse fetch), mas a empresa é lucrativa e
  solvente (patrimônio +US$81,5 bi, lucro TTM +US$21,0–26,8 bi) — ROE real
  gira em **~26–33%**, uma força genuína que o gate estava escondendo.
- **IBRX**: mesma ausência (`returnOnEquity=None`), mas o **patrimônio é
  negativo** (−US$500 mi, déficit acumulado típico de biotech pré-receita) —
  ROE = lucro/patrimônio com denominador negativo produz um número
  **matematicamente enganoso** (sondagem ao vivo do Finnhub confirmou:
  `roeTTM = -193,29%`, não um gap de coleta, o vendor devolve um valor real só
  que sem sentido econômico).

Um único tratamento ("sempre derivar" ou "sempre isentar") quebraria um dos
dois casos. Decisão (confirmada com o usuário): **discriminar pelo sinal do
patrimônio**, e para o caso recuperável, **reconciliar via Finnhub** (fonte já
integrada, ADR-030) em vez de derivar localmente das demonstrações capturadas.

1. **`providers/yahoo.py::_stockholders_equity`** extrai o patrimônio mais
   recente do balanço anual (`Stockholders Equity`/variantes). Quando `roe`
   vem ausente do Yahoo **e** `equity ≤ 0`, o campo entra em
   `not_applicable_fields` (mesmo mecanismo do PE) — nunca reconciliado por
   uma fonte secundária, então o −193% do Finnhub nunca sobrescreve o
   `not_applicable` (`reconcile_critical_fields` só substitui status em
   `{missing, unavailable, invalid, stale}`, `not_applicable` fica de fora
   desse conjunto por design já existente — nenhuma mudança necessária no
   motor de reconciliação).
2. Quando `equity > 0` (caso JNJ), `roe` continua `missing` — dentro do
   conjunto reconciliável — e **`providers/finnhub.py::FinnhubMarketDataProvider`
   passa a expor `roe`** (`supported_fields` ganha `"roe"`; valor vem de
   `metric.roeTTM`, convertido de percentual para fração via
   `_ratio_from_percent` para casar a escala do `returnOnEquity` do Yahoo).
   `application/collection.py`/`config/settings.json::provider_critical_fields`
   ganham `"roe"`, então a cadeia de reconciliação já existente
   (`reconcile_critical_fields`, Finnhub é o primeiro secondary fetcher)
   preenche o valor real quando o Yahoo tem o gap.

Testes: `tests/test_finnhub_provider.py` (ROE convertido corretamente,
`supported_fields` atualizado), `tests/test_yahoo_provider_contract.py`
(`_stockholders_equity` lê a coluna mais recente; reconciliação preenche ROE
quando `equity>0`; reconciliação **nunca** sobrescreve `not_applicable` mesmo
com secundária presente), `tests/test_governed_config.py` (novo campo pinado
em `provider_critical_fields`). 1.068 testes verdes.
