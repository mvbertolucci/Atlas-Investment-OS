# Changelog — PR-015.5D

## Changed

- A aba `Decision Analysis` agora é gerada a partir de
  objetos `CompanyReport`.
- A transformação para DataFrame ocorre somente no limite
  da apresentação Excel.

## Compatibility

- Ranking, Summary, Opportunity Analysis, Explainability,
  Diagnostics e relatórios históricos foram preservados.
- A assinatura pública de `write_latest_and_history()` não mudou.
