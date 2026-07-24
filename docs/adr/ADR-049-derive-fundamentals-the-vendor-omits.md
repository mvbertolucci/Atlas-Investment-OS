# ADR-049 — Derivar das demonstrações os fundamentos que o fornecedor omite

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `providers/yahoo.py`, ADR-047 (frescor por cadência, que
  tornou este caso visível), ADR-048 (`roe` fora da concordância crítica —
  pré-requisito), ADR-037 adendo (mesma lacuna do JNJ, então sem solução),
  ADR-012/ADR-044 (percentis na seção cruzada — a razão de a *definição*
  importar)

## Contexto

Investigando os campos que continuavam `stale`/ausentes depois da ADR-047, o
JNJ apareceu com **confiança 59** — abaixo do gate de 70, bloqueando decisão —
por `business:roe` ausente.

A causa não é falha de rede nem da paralelização: o `info` do Yahoo para o JNJ
tem **173 chaves e simplesmente não inclui** `returnOnEquity`, `freeCashflow`,
`operatingCashflow`, `quickRatio`, `currentRatio`. O MSFT tem 180 e traz todas.
As chaves estão **ausentes do payload**, não nulas, e de forma persistente
(três buscas seguidas). É lacuna de cobertura do fornecedor para o emissor — o
mesmo caso já registrado no adendo do ADR-037, à época sem solução.

Dimensionado no snapshot de 2026-07-24: **1 de 18** posições da carteira (JNJ)
e **6 de 117** símbolos coletados têm ao menos um desses campos ausente.

Os insumos, porém, estão nas demonstrações que **já baixamos**.

## A definição importa mais que a disponibilidade

O score compara **percentis na seção cruzada** (ADR-012; o ADR-044 corrigiu
justamente uma inconsistência de universo). Um campo derivado por régua
diferente da usada nos outros ~2.900 papéis não completa a comparação: a
distorce, e silenciosamente.

Por isso cada fórmula candidata foi medida **contra os próprios valores do
Yahoo**, nos tickers em que ele publica o campo:

| Campo | Fórmula testada | Erro vs Yahoo | Decisão |
|---|---|---|---|
| `roe` | lucro TTM ÷ patrimônio **final** | 5–12% (viés sistemático) | rejeitada |
| `roe` | lucro TTM ÷ patrimônio **médio** (atual e 4T atrás) | **≤0,4%** | **adotada** |
| `current_ratio` | ativo circ. ÷ passivo circ. | **exato** | rejeitada (ver abaixo) |
| `operating_cashflow` | soma de 4 trimestres | **≤0,1%** | **adotada** |
| `free_cashflow` | soma da linha "Free Cash Flow" de 4T | **17–97%** | rejeitada |
| `quick_ratio` | (circulante − estoque) ÷ passivo circ. | **3,6–16,4%** | rejeitada |

Duas rejeições valem registro, porque a intuição diz que funcionariam:

- **`free_cashflow`**: o `freeCashflow` do Yahoo é *levered* (após juros e
  amortização), não `OCF − capex`. MSFT: 72,9 bi somando os trimestres contra
  **37,0 bi** publicados. META: 48,3 contra 25,6.
- **`quick_ratio`**: o Yahoo exclui mais que estoque do numerador.

Preencher esses dois com definição própria seria pior que a ausência — a
ausência é visível, o viés não.

## Decisão

Derivar **apenas** `roe` e `operating_cashflow`, e **apenas quando a chave do
fornecedor estiver ausente** (`raw_presence` falso). Onde o Yahoo publica,
nada muda.

- `roe` sai do `quarterly_balance_sheet`, **já buscado** — custo zero.
- `operating_cashflow` precisa do `quarterly_cashflow`, buscado de forma
  **preguiçosa**: só o emissor com a lacuna paga a chamada extra (6 de 117 na
  medição), preservando o orçamento de 6 chamadas/símbolo da ADR-046.

### `current_ratio` fica de fora, apesar da fórmula estar certa

A primeira versão derivava também `current_ratio` — fórmula exata contra o
Yahoo. A validação com recoleta real mostrou que **isso piorava o campo**: ele
está em `provider_critical_fields` e portanto já tinha caminho de fallback
secundário funcionando. O `quarterly_balance_sheet` do Yahoo para o JNJ parava
em **2026-03-31** enquanto o SEC já tinha o 10-Q de **junho**; o valor derivado
(1,0252) entrava como primário, deslocava o secundário mais fresco (1,0889),
discordava dele em **5,85%** — logo acima da tolerância de 5% — e os dois eram
descartados. O campo ia de `present` para `invalid`.

Princípio que fica: **derivação é para campo sem outra fonte.** Onde existe
secundário, ele vem primeiro — derivar preempta um dado possivelmente mais
fresco e ainda arrisca a anulação por divergência que a ADR-048 acabou de
tratar.

O campo derivado fica **auditável**: evidência com `source: "Atlas derived"` e
`detail` nomeando a fórmula e o erro medido, visíveis na página da empresa.

**Depende da ADR-048.** Derivar `roe` mantendo-o na concordância crítica só
recriaria a anulação por divergência de definição que aquele ADR resolveu.

## Alternativas consideradas

- **Derivar sempre, para todos os símbolos.** Daria régua uniforme e
  resolveria a preocupação de percentil de vez, mas mudaria o valor de ~2.900
  papéis e exigiria revalidar o modelo inteiro. Desproporcional para 5% de
  cobertura.
- **Buscar no secundário (SEC/Finnhub).** Menos código novo, mas reintroduz
  mistura de definições entre fornecedores — exatamente o que causou a
  ADR-048.
- **Aceitar a ausência.** Deixaria o JNJ travado abaixo do gate por uma
  lacuna do fornecedor, com o dado necessário já em disco.

## Consequências

- JNJ passa a ter `roe` **0,2641** — dentro da faixa de 26–33% que o adendo do
  ADR-037 já apontava como o ROE real — e `operating_cashflow` 22,87 bi, ambos
  marcados como derivados. Confiança **59,0 → 90,0**, `Missing Required
  Features` volta a `Nenhum`: o gate destrava.
- `free_cashflow` e `quick_ratio` do JNJ **seguem ausentes**, deliberadamente.
  Nenhum dos dois é feature obrigatória, então não travam o gate.
- MSFT e demais emissores com cobertura normal: **inalterados** (verificado ao
  vivo — todos os campos continuam com `source: Yahoo Finance`).
- Custo de requisição inalterado para ~95% do universo.
- **Risco assumido**: se o Yahoo mudar a definição de `returnOnEquity`, a
  derivação passa a divergir sem alarme. Mitigado por a fórmula estar medida e
  documentada aqui, e pelo `detail` registrar o erro esperado.

## Verificação

- `tests/test_yahoo_provider_contract.py` — 6 testes novos: média de
  patrimônio (trava que o final, que erra 5–12%, não é usado), recusa por
  histórico insuficiente, recusa para balanço sem circulante segregado,
  soma de exatamente 4 trimestres, recusa com ano parcial.
- Suíte completa: **1212 testes verdes**.
- Verificado ao vivo antes e depois, com recoleta real da carteira.
