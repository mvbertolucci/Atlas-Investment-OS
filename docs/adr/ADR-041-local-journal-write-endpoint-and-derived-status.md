# ADR-041 — Endpoint local de escrita no journal e status derivado no cockpit

- **Status**: Accepted
- **Data**: 2026-07-22
- **Relacionado**: `api/server.py`, `api/resources.py`, `decision/status.py`, `decision/cockpit.py`, ADR-040 (identidade estável, pré-requisito), `docs/DECISION_JOURNAL.md`

## Contexto

O Decision Journal existia desde os commits `a83b771`..`7af6cb0`, mas
`decision_journal.json` tinha **zero eventos**: a única forma de registrar uma
revisão humana era a CLI `python -m decision.journal <hash-de-16-chars> ...`.
O atrito de copiar um hash para o terminal era grande o bastante para o ciclo
humano nunca fechar. Uma "fila persistente de decisões" sem registro humano é
apenas outro relatório.

A API (`api/server.py`) era deliberadamente read-only e a doc afirmava "não
existe endpoint web de escrita". Habilitar a interatividade exige rever essa
postura de forma consciente.

## Decisão

1. **`POST /journal`** — único caminho de escrita da API. Recebe
   `{decision_id, status, reason}`, localiza a decisão na Decision Queue
   corrente e delega a `record_decision` (mesma validação da CLI). A
   identidade estável do ADR-040 é o que torna isso útil: o evento registrado
   sobrevive a execuções seguintes.
2. **Cockpit servido pela própria API** (`GET /cockpit`) para que os botões
   Aceitar/Adiar/Rejeitar façam `fetch` same-origin. Aberto via `file://`, os
   botões são desativados com um aviso — nenhuma escrita cross-origin.
3. **Status derivado, não armazenado** (`decision/status.py`): `novo`,
   `em análise` (DEFERRED), `decidido` (ACCEPTED), `descartado` (REJECTED),
   `executado` (fill no ledger, que domina). Computado de journal + ledger a
   cada render — evita um quinto vocabulário de status persistido que poderia
   dessincronizar das três fontes já existentes (grupos da fila, status do
   journal, status do ledger).

### Postura de segurança (ferramenta local pessoal)

- Servidor liga apenas em `127.0.0.1`; não deve ser exposto em rede.
- A escrita exige `Content-Type: application/json` — um formulário cross-site
  não consegue defini-lo sem preflight CORS (que não respondemos), mitigando
  CSRF simples.
- Corpo limitado (64 KiB); método/rota em allowlist (POST só em `/journal`).
- Append-only e consultivo: nunca envia ordem nem muta a carteira. `record_decision`
  já rejeita duplicatas exatas.
- Sem autenticação — aceitável para uma ferramenta local de um único usuário
  em loopback; **não** promover a multiusuário/rede sem repensar isto.

## Alternativas consideradas

- **Manter só a CLI**: preserva a postura read-only, mas mantém o atrito que
  deixou o journal vazio. Rejeitada — o objetivo do PR era fechar o ciclo.
- **Botão "copiar comando CLI"**: zero superfície nova, mas não é um clique.
  Oferecida ao usuário; ele escolheu o endpoint HTTP.
- **Formulário → arquivo aplicado no próximo run**: assíncrono e mais
  complexo, adia o efeito. Rejeitada.
- **Status persistido**: rejeitado por criar segunda fonte de verdade.

## Consequências

- A doc "não existe endpoint web de escrita" deixou de valer; atualizada em
  `docs/DECISION_JOURNAL.md` e `STATUS.md`.
- O cockpit passa a ter duas formas de uso: `file://` (só leitura) e
  `http://127.0.0.1:8000/cockpit` (interativo). O run principal continua
  gerando o arquivo estático normalmente.
- Validado por smoke test HTTP isolado (paths temporários): POST legítimo
  201; form sem json 415; POST fora de `/journal` 404; `/cockpit` 200; status
  derivado vira `decidido`. O journal real não foi tocado.

## Rollback

Reverter o commit: a API volta a ser read-only, o cockpit volta a ser estático
sem botões. Eventos já gravados no journal permanecem válidos (o formato não
mudou; `POST /journal` usa o mesmo `record_decision` da CLI).
