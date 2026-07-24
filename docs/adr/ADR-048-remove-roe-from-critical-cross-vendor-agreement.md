# ADR-048 — Remover `roe` da concordância crítica entre fontes

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `config/settings.json`,
  `providers/yahoo.py::DEFAULT_CRITICAL_FIELDS`,
  `providers/evidence.py::reconcile_critical_fields`, ADR-042 (mesmo remédio
  para `total_debt`), ADR-038 (idem para `market_cap`/`enterprise_value`/
  `short_float`/`total_cash`), ADR-047 (a mudança que expôs isto)

## Contexto

A ADR-047 corrigiu a datação dos fundamentos, e a recoleta da carteira real
mostrou o ganho esperado: **324 → 3** campos `stale`, confiança média
**64,8 → 92,6**, posições abaixo do gate de 70 caindo de **15 para 2**.

Mas duas posições andaram para trás, e uma delas **mudou decisão**:

```
ASML   confiança 73,0 → 59,0      —      → REVISAR
CLF    confiança 76,4 → 59,0    SELL     → REVISAR
```

59,0 é exatamente o `missing_required_cap` de `config/model.yaml`. Ambas
passaram a acusar `business:roe` ausente, depois de oito execuções seguidas
com `Nenhum`.

### Mecanismo

O `roe` estava em `provider_critical_fields`, sujeito à checagem cruzada de
`reconcile_critical_fields`, que anula o campo (`INVALID`, "critical sources
disagree") quando primário e secundário divergem além de 5%.

**Enquanto o `roe` vivia permanentemente `stale`, ele nunca era reconciliado**
— `reconcile_critical_fields` trata `STALE` como primário inutilizável e pula a
comparação. A divergência existia desde sempre, invisível.

Ao ser datado corretamente pela ADR-047, o campo virou `PRESENT`, entrou na
reconciliação pela primeira vez e foi anulado. E `INVALID`, ao contrário de
`STALE`, **não** conta como "tem valor" em `metric_has_value` (ADR-014 /
correção de 2026-07-20), então o teto de confiança disparou.

### A divergência é definicional, não erro

| | Yahoo (TTM) | Finnhub | Distância |
|---|---|---|---|
| ASML | 0,5394 | 0,4468 | 17% |
| CLF | −0,1386 | −0,2091 | 34% |

Nenhum dos dois está errado. O `returnOnEquity` do Yahoo é lucro líquido TTM
sobre patrimônio; o Finnhub usa outra base de período e/ou patrimônio médio em
vez de final. **Exigir 5% de concordância entre duas definições diferentes é
inatingível por construção** — a mesma conclusão do ADR-042 para `total_debt`
(soma SEC desalinhada anulando o valor correto do Yahoo em ~48% das posições) e
do ADR-038 para `market_cap`/`short_float`.

## Decisão

Remover `roe` de `provider_critical_fields`. O valor do Yahoo passa a ser
aceito nativamente, sem exigir concordância com o secundário.

Diferente do ADR-042, **um único lugar muda**: `roe` estava só em
`config/settings.json` (a lista autoritativa). `providers/yahoo.py::
DEFAULT_CRITICAL_FIELDS` e o default de `universe/collector.py` nunca o
tiveram. O comentário do `yahoo.py` — sítio canônico onde as ausências
deliberadas são explicadas — ganhou a justificativa do `roe`.

`roe` mantém evidência de campo própria (presente/ausente/velho); só deixa de
ser **anulado** por divergência de definição.

## Alternativas consideradas

- **Reconciliação ciente de definição** (comparar só quando as bases de
  período baterem). Conceitualmente superior e a resposta certa a prazo, mas
  exige metadados de período que o secundário não expõe de forma confiável.
  Não bloqueia esta correção.
- **Alargar a tolerância para `roe`.** Um número que cobrisse 34% (CLF)
  aceitaria praticamente qualquer coisa, esvaziando a checagem sem admitir
  que ela não se aplica a este campo.
- **Aceitar e revisar manualmente.** Deixaria um SELL legítimo suprimido por
  um artefato de metodologia.
- **Reverter a ADR-047.** Devolveria o `SELL` do CLF ao custo de reintroduzir
  324 campos falsamente defasados — e apenas re-esconderia a divergência.

## Consequências

Verificado com recoleta real da carteira (backup do histórico antes; ver
"Verificação"):

| | original | pós ADR-047 | pós ADR-048 |
|---|---|---|---|
| Confiança média | 64,8 | 92,6 | **94,6** |
| Abaixo do gate de 70 | 15 | 2 | **1** |
| Campos `stale` | 324 | 3 | **3** |

- **ASML 59,0 → 94,8** e **CLF 59,0 → 93,8**; o `SELL` do CLF voltou.
- Decisões finais: `SELL` em AVAV, CLF, FMC, SGML; `REVISAR` em IBRX, JNJ, YPF.
- Os 3 `stale` remanescentes são legítimos: `short_float` (BRK-B) e
  `free_cashflow`/`fcf_yield` (JNJ), ausentes na fonte.
- **Risco assumido**: um `roe` genuinamente errado do Yahoo deixa de ser
  barrado pelo secundário. Aceito pelo mesmo argumento do ADR-042 — o campo
  segue coberto por evidência própria e pelos deal breakers, e a checagem
  cruzada não conseguia distinguir erro de diferença de definição.

### Não confundir com a intermitência do JNJ

Na recoleta de validação, **JNJ caiu de 94,0 para 59,0** por `business:roe`
ausente. **Não é efeito deste ADR** — remover um campo da reconciliação só pode
evitar anulação, nunca criar ausência. Medido: `roe` do JNJ estava `present`
em todas as execuções até 11:36 e `missing` às 11:47; três buscas consecutivas
ao provider devolveram `None`. É o Yahoo oscilando `returnOnEquity` para o JNJ
ao longo do dia — o mesmo gap já registrado no adendo do ADR-037 (patrimônio
+US$81,5bi e lucro TTM positivo; o ROE real é ~26–33%). Fica como problema
aberto, independente deste ADR.

## Verificação

- `tests/test_provider_evidence.py::test_definitional_disagreement_no_longer_nulls_roe`
  — trava que a divergência medida (0,5394 vs 0,4468) não anula mais o campo.
- `...::test_roe_would_still_be_nulled_if_declared_critical` — guarda de
  mecanismo: a mudança é de **política** (quais campos são críticos), não do
  reconciliador; se alguém redeclarar `roe` crítico, este teste falha e aponta
  a causa.
- `tests/test_governed_config.py` — pin de `provider_critical_fields`
  atualizado (config governada, mudança deliberada).
- Suíte completa: **1206 testes verdes**.
- Backup do histórico antes da recoleta:
  `data/atlas_history.backup_20260724_113256.db` + contratos JSON em
  `data/backup_dados_20260724_113256/`.
