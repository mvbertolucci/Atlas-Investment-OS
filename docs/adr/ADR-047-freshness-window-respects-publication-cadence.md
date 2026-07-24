# ADR-047 — Frescor ancorado na cadência de divulgação do emissor, e TTM datado pelo trimestre

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `providers/yahoo.py`, `providers/evidence.py`,
  `config/data_quality.yaml`, ADR-037 (ausência estrutural ≠ falha de coleta —
  mesmo princípio, agora no eixo temporal), ADR-039 (redução de REVISAR por
  causa não acionável)

## Contexto

Rodando a carteira real, AVAV apareceu com **Confiança 37,5** e a mensagem
"Cobertura de dados abaixo do usual para os fatores exigidos", **logo após uma
atualização completa**. A orientação exibida ao usuário era recoletar o ticker
— ação que não mudaria nada. Dos 83 campos, **20 estavam `desatualizado`**,
quase todos fundamentos, todos observados em **30/04/2026**.

O usuário formulou o problema com precisão: *"muitas empresas ainda não
divulgaram resultados de junho, não faz sentido dizermos que está desatualizado
se temos resultado de março ou abril"*.

### Medição na carteira real (18 posições, snapshot 2026-07-24)

A hipótese inicial deste ADR — "alargar a janela de 35 para ~135 dias" — foi
**derrubada pela medição**, e vale registrar por quê. As idades dos 324 campos
`STALE` não formavam uma distribuição contínua: concentravam-se em **quatro
valores discretos**.

| Idade | Data | Natureza |
|---|---|---|
| ~1 dia | 23/07/2026 | mercado |
| 85 dias | 30/04/2026 | trimestre mais recente (AVAV, ano fiscal em abril) |
| **205 dias** | **31/12/2025** | **exercício anual** |
| 208 dias | 28/12/2025 | anual, calendário 52/53 semanas (JNJ) |
| 389 dias | 30/06/2025 | anual, ano fiscal em junho (MSFT) |

Mediana: **205 dias**. Não era defasagem de publicação — era o quadro **anual**.
Alargar a janela para ~135 dias resolveria só 46% dos casos; calibrá-la pela
mediana observada teria **escondido** a causa real.

### Os dois defeitos

**1. Valor TTM carimbado com a data do exercício anual.**
`providers/yahoo.py` buscava `financials` e `cashflow` (quadros **anuais**) só
para extrair `observed_at`, enquanto os **valores** vinham de `info`
(`defaultKeyStatistics`/`financialData`), que o Yahoo publica em base
*trailing twelve months*. Verificado contra o snapshot bruto do MSFT:

| Fonte | EBITDA |
|---|---|
| Exercício anual FY2025 (encerrado 30/06/2025) | 160,165 bi |
| `record["ebitda"]`, vindo de `info` | **184,457 bi** |

São grandezas distintas — `net_margin` idem (0,3934 no registro contra
0,3615 no anual). O número cobria até o último trimestre fechado, mas era
datado com o fim do exercício, até 12 meses antes. No MSFT o descolamento era
de **um ano inteiro**: balanço em 2026-03-31, fluxo carimbado em 2025-06-30.

**2. Janela de frescor puramente cronológica.**
`providers/evidence.py` aplicava `freshness.acceptable_days` (35) a todo campo
`PRESENT`, sem olhar categoria. O comentário do `config/data_quality.yaml`
revelava a calibração original — *"A coleta ampla é mensal"* — isto é, a janela
media a cadência da **nossa coleta**, não a do **fato observado**. Um
fundamento trimestral passa a maior parte da vida útil acima de 35 dias; um
semestral, quase toda ela.

**Nenhum dos 324 campos era falha de coleta.** Inclusive o BTI, único que
sobrava depois das duas correções: é do Reino Unido e reporta
**semestralmente** — em 24/07/2026, 31/12/2025 era genuinamente o período mais
recente publicado.

## Decisão

Separar **defasagem de publicação** (ninguém tem dado mais novo) de
**defasagem de coleta** (existe mais novo e não pegamos). Só a segunda desconta
confiança.

### 1. Datar o TTM pelo trimestre (`providers/yahoo.py`)

Os campos de fluxo — `roe`, `roa`, margens, `ebitda`, `free_cashflow`,
`operating_cashflow` — passam a ser datados por `mostRecentQuarter` (fallback:
quadro anual), em vez do fim do exercício.

**Nenhum valor muda**: os números já eram TTM, que é a base escolhida. Muda só
a data atribuída a eles.

**Sem custo de requisição.** A primeira versão desta mudança buscava
`quarterly_financials` e `quarterly_cashflow`, o que levaria `fetch_symbol` de
6 para 8 chamadas HTTP por símbolo — 33% a mais sobre a base com que a ADR-046
dimensionou a paralelização, e a coleta ampla já opera no teto de 2 req/s.
Medido em 4 emissores, os dois quadros extras não acrescentavam nada:

| | BTI | MSFT | AVAV | JNJ |
|---|---|---|---|---|
| Cadência via `quarterly_balance_sheet` (já buscado) | 182 | 91 | 92 | 91 |
| Cadência via os 3 quadros trimestrais | 182 | 91 | 92 | 91 |
| `mostRecentQuarter` (grátis, vem no `info`) | 2025-12-31 | 2026-03-31 | 2026-04-30 | 2026-06-28 |
| `_statement_date(quarterly_financials)` | **None** | 2026-03-31 | 2026-04-30 | 2026-06-30 |

Idênticos, exceto por 2 dias no JNJ (calendário 52/53 semanas — e a data
gratuita é a do trimestre fiscal real), e o caminho gratuito ainda é mais
robusto: no BTI o quadro trimestral de resultado voltou vazio.

### 2. Frescor por cadência do emissor (`providers/evidence.py`)

Para as categorias em `freshness.period_cadence_categories` (hoje
`fundamentals`), o limite deixa de ser `acceptable_days` e passa a ser
**`reporting_period_days + filing_lag_days`**: o dado só envelhece quando o
período *seguinte* já deveria ter sido publicado.

`reporting_period_days` é medido pelo provider a partir do espaçamento mediano
entre períodos consecutivos do **próprio emissor**, lidos do
`quarterly_balance_sheet` que já era buscado (`_reporting_period_days`, prefixo
`_` para ficar fora de `field_evidence`). Isso cobre trimestral (~91d)
e semestral (~182d) **sem configuração por ticker** — e, por ancorar no período
fiscal de cada um, cobre também ano fiscal em abril (AVAV), em junho (MSFT) e
calendário 52/53 semanas (JNJ).

Mercado, analista, identidade e propriedade seguem com a janela cronológica de
35 dias: bolsa não tem calendário de divulgação.

`max_reporting_period_days: 400` limita o estrago de uma série malformada.

## Alternativas consideradas

- **Alargar a janela global.** Hipótese original, rejeitada pela medição:
  resolve 46%, e calibrada pela mediana da carteira esconderia o defeito de
  datação por completo.
- **Aceitar `STALE` na cobertura** (estender `metric_has_value` a
  `metric_available`). Uma linha, mas elimina a distinção temporal: dado de
  2019 passaria a valer como o de ontem.
- **Reconstruir TTM somando 4 trimestres.** Desnecessário — o `info` do Yahoo
  já entrega TTM, verificado numericamente contra o quadro anual.
- **Usar o trimestre isolado** em vez de TTM. Margens de um trimestre são
  sazonais e voláteis; pioram a comparação entre empresas.
- **Baixar `min_confidence_score`.** Trata o sintoma e degrada o gate para
  todos os casos, inclusive os de baixa confiança legítima.

## Consequências

Verificado ao vivo (chamada direta ao provider, sem escrita em histórico):

| Ticker | Cadência medida | Fluxo: antes → depois | `stale` antes → depois |
|---|---|---|---|
| AVAV | 92 d | 2026-04-30 → 2026-04-30 | 20 → **0** |
| MSFT | 91 d | **2025-06-30 → 2026-03-31** | 20 → **0** |
| BTI | **182 d** | 2025-12-31 → 2025-12-31 | 20 → **0** |
| JNJ | 91 d | 2025-12-31 → 2026-06-28 | 8 → **0** |

- Confiança e Data Coverage deixam de oscilar com o calendário de divulgação;
  o gate `min_confidence_score: 70` volta a significar dado genuinamente
  insuficiente.
- **O sinal sobrevive**: passado período + prazo de arquivamento, o campo volta
  a ser `STALE` (coberto por teste). O teto de 400 dias impede que uma cadência
  malformada vire janela infinita.
- 1204 testes verdes, incluindo 7 novos que fixam os casos reais medidos (AVAV
  trimestral no ciclo, BTI semestral a 205 dias, gap real além do prazo, campo
  de mercado mantendo a janela cronológica, teto de cadência, fallback, e o
  texto de baixa cobertura sem campo obrigatório faltando).
- `test_governed_config.py` teve o pin de `data_quality.yaml` atualizado — a
  política é governada e a mudança é deliberada.

### Orientação ao usuário (mesma sessão)

O texto do cockpit afirmava "recolete {ticker}" como remédio para toda baixa
confiança sem divergência de fonte. No AVAV isso mandava executar uma ação
inútil: nenhum campo obrigatório faltava — `missing_evidence` (features
obrigatórias + evidência de risco) vinha **vazio**, e a mensagem caía num ramo
genérico que mesmo assim asseverava o remédio.

`decision/cockpit.py::_confidence_explanation` ganhou um terceiro ramo: sem
campo obrigatório ausente, deixa de afirmar que recoletar resolve e aponta a
página da empresa (`/company/SYM`, ADR-045), onde situação e data de cada campo
estão visíveis. Recoletar segue sendo a orientação quando há campo ausente de
fato.

`reports/evidence_reasons.py::_status_phrase` traduz o novo `detail` de
cadência: com a ADR-047, `stale` num fundamento deixou de significar "passou do
relógio" e passou a significar "o período seguinte já venceu o prazo de
divulgação e não foi coletado" — e é justamente nesse caso que recoletar
resolve.

## Migração / rollback

Sem migração de dado: `STALE` é recalculado a cada avaliação, nunca persistido
como verdade. Rollback da parte 2 é remover `period_cadence_categories` do YAML
(o fallback global de 35 dias volta a valer para tudo); da parte 1, reverter o
`observed_at` dos campos de fluxo para `_statement_date(income_statement)` —
mas isso restaura um carimbo comprovadamente errado.
