# ADR-040 — Identidade estável de decisão e snapshot da fila por execução

- **Status**: Accepted
- **Data**: 2026-07-22
- **Relacionado**: `decision/queue.py`, `decision/journal.py`, `decision/execution.py`, ADR relacionados à camada decisória (queue/cockpit/journal/ledger, commits `d02436f`..`7af6cb0`)

## Contexto

O `decision_id` era `sha256(generated_at|symbol|action|engine)` — o
timestamp da execução fazia parte da identidade. Consequência medida no
estado real: o ID de "SELL AVAV" muda a cada run, então um evento
registrado no Decision Journal hoje aponta para um ID que não existe na
fila de amanhã. A "fila persistente" era, por construção, um retrato
diário: impossível acompanhar novo → em análise → decidido entre dias.
O sintoma concreto é `decision_journal.json` com **zero eventos** — o
fluxo humano nunca fechou o ciclo.

Além disso, `decision_queue.json` era sobrescrito a cada execução, sem
histórico, o que impede qualquer comparação "o que mudou desde a última
execução" (a lacuna de maior valor apontada na revisão de UX do fluxo
decisório de 2026-07-22).

## Decisão

1. **Identidade estável**: `decision_id = sha256(symbol|action|engine)[:16]`,
   sem `generated_at`. O timestamp permanece no payload
   (`generated_at` da fila, `queue_generated_at` no journal) como
   atributo de ocorrência, não de identidade. Journal e ledger passam a
   acompanhar a mesma decisão ao longo de dias sem mudança de código —
   `journal_summary` ("último status por decision_id") passa a
   significar "status humano corrente da decisão", e a exigência do
   ledger de um ACCEPTED prévio continua válida entre execuções.
2. **Guarda de colisão**: `build_decision_queue` levanta `ValueError` se
   dois itens da mesma execução produzirem o mesmo ID (hoje impossível —
   cada motor emite no máximo um item por símbolo — a guarda protege
   contra regressão silenciosa que corromperia o journal).
3. **Snapshot por execução**: `snapshot_decision_queue` grava uma cópia
   imutável em `output/dados/history/decision_queue/decision_queue_<generated_at>.json`
   (via `atomic_write_json`, ADR-032) — sob `dados/` porque é contrato
   JSON interno, como o resto da camada decisória. É a base do diff
   run-over-run ("mudou desde ontem"), próximo incremento planejado.
4. **Contrato**: `DECISION_QUEUE_VERSION` 1.0 → 1.1 (semântica do
   `decision_id` mudou). Nenhum consumidor valida a versão da fila
   estritamente; journal e ledger resolvem IDs contra a fila corrente.

## Alternativas consideradas

- **Manter o ID por execução e mapear equivalência no journal**
  (tabela decision_id-antigo → novo): empurra a complexidade para todos
  os consumidores e mantém duas identidades vivas. Rejeitada.
- **Incluir o `reason` na identidade**: faria o ID mudar quando só o
  texto explicativo muda, reabrindo o problema original. Rejeitada.

## Consequências

- Um evento do journal sobrevive a execuções subsequentes; o mesmo
  símbolo+ação+motor é uma decisão, não N retratos.
- Se a **mesma** decisão reaparecer meses depois de resolvida (vendeu,
  recomprou, novo sinal SELL), o ID é o mesmo — o histórico do journal
  conta a história completa por ordem temporal, que é o comportamento
  auditável desejado; consumidores devem ler "último evento", como
  `journal_summary` já faz.
- `output/history/` não é versionado (runtime artifact, `.gitignore`).

## Migração/rollback

- Migração de dados: nenhuma — o journal estava vazio no momento da
  mudança (janela deliberadamente aproveitada). O ledger idem.
- Rollback: reverter o commit; snapshots antigos permanecem válidos como
  JSON independentes.
