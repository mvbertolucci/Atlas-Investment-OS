# ADR-052 — `Decision Confidence` baixa não é história de dado

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `decision/cockpit.py`, `decision/engine.py`,
  ADR-047 (mesmo sintoma no AVAV, outra causa — lá a datação do TTM era o
  defeito; aqui é o rótulo), ADR-039 (redução de REVISAR por causa não
  acionável)

## Contexto

Mesmo depois da ADR-047 zerar os campos `STALE` do AVAV, o cockpit seguia
exibindo:

> **Confiança baixa.** Cobertura de dados abaixo do usual para os fatores
> exigidos. […] Nenhum campo obrigatório está faltando — a cobertura é puxada
> por campos secundários.

Medido no `decision_queue.json` da execução de 2026-07-24 15:18:

| Campo | Valor |
|---|---|
| `data_coverage` | **98,3** |
| `decision_confidence` | **55,6** |
| `conviction_score` | 61,4 |
| `opportunity_score` | 14,6 |
| `risk_penalty` | 15,0 |
| `missing_evidence` | `[]` |

A cobertura estava em 98,3 — quase perfeita. O número abaixo do piso 60 era
`decision_confidence`, e ele reproduz exatamente a fórmula de
`decision/engine.py::_decision_confidence`:

```
61,4·0,50 + 98,3·0,30 + 14,6·0,20 − 15,0·0,50 = 55,6
```

**`Decision Confidence` não mede evidência.** Mistura convicção (50%),
cobertura (30%), oportunidade (20%) e desconta metade da penalidade de risco.
Cai por construção em empresa mal avaliada — que é o caso do AVAV (`AVOID`,
Investment Score 22,3). Déficit por termo: convicção 19,3, oportunidade 17,1,
risco 7,5, **cobertura 0,5**.

`_confidence_explanation` disparava com `decision_confidence OU data_coverage`
abaixo do piso e, em qualquer um dos casos, contava uma história de dado. Duas
afirmações eram falsas para o AVAV: a de que a cobertura estava abaixo do usual
(estava em 98,3) e a de efeito — "mantém em revisão em vez de agir" — quando o
item estava no grupo `EXECUTE` com ação `SELL`.

## Decisão

Separar o eixo **evidência** do eixo **tese**. Com `missing_evidence` vazio
**e** `data_coverage` acima do piso, o bloco deixa de falar de dado e passa a
decompor a nota: informa a cobertura real, os pesos da fórmula e nomeia os dois
maiores déficits (`_composite_confidence_explanation`).

A cobertura fica **fora** da lista de culpados nesse ramo — este ramo só existe
porque ela está acima do piso.

O efeito exibido também foi corrigido: `decision_confidence` alimenta o sinal
de qualidade da carteira (`portfolio/quality.py`, peso 0,15;
`portfolio/rebalance.py::_quality_signal`) e **não é gate** — não segura a ação
sugerida no card.

Ordem dos ramos, do mais específico ao mais geral:

1. `missing_evidence` presente → explicação campo a campo (inalterado).
2. `data_coverage` abaixo do piso → cobertura genérica (inalterado).
3. Nenhum dos dois → nota composta.

## Alternativas consideradas

- **Disparar só por `data_coverage`.** Esconderia a confiança baixa do card em
  vez de explicá-la — e o número segue visível no metadado.
- **Renomear `Decision Confidence` para `Decision Score`.** Corrige a raiz do
  engano, mas o nome atravessa `reports/excel.py`, `outcomes/models.py`,
  histórico persistido e o contrato da fila. Fica registrado como dívida.
- **Baixar o piso de 60.** Trata o sintoma e cega o cockpit para baixa
  confiança legítima.

## Consequências

Bloco renderizado com os dados reais do AVAV:

> **Confiança da decisão baixa — não é falta de dado.** A cobertura de dados
> está em 98 — o dado está lá. A nota combina convicção (50%), cobertura (30%)
> e oportunidade (20%), menos metade da penalidade de risco; aqui ela é puxada
> por convicção em 61 e oportunidade em 15.

- 1243 testes verdes, incluindo o novo caso de aceitação com os números medidos.
- `test_low_coverage_without_missing_field_does_not_assert_recollection`
  (ADR-047, cobertura 62,2 e nenhum campo ausente) migrou para o ramo composto:
  62,2 está **acima** do piso, então a resposta honesta ali também é a nota
  composta. As garantias do teste — não mandar recoletar, apontar `/company` —
  seguem verificadas.
- O ramo genérico de cobertura sobrevive para o caso real dele: cobertura
  abaixo de 60 sem campo obrigatório ausente.

## Migração / rollback

Sem migração: o bloco é recalculado a cada render. Rollback é remover o ramo 3
de `_confidence_explanation` — o que restaura uma afirmação comprovadamente
falsa sobre a cobertura.
