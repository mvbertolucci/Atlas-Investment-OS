# ADR-046 — Paralelização de coleta: ThreadPoolExecutor com limite global

- **Data**: 2026-07-24
- **Status**: Aceito
- **Contexto**: Coleta ampla de universo (2930 símbolos) parada em 69% após ~12 horas; sequencial é o gargalo.

## Contexto

Cada símbolo custa ~6 requisições HTTP sequenciais ao Yahoo (info, history, balance_sheet, quarterly_balance_sheet, financials, cashflow). Uma coleta completa gasta **~3,9s por símbolo**, totalizando ~60 min para 901 restantes.

O rate limit de `2 req/s` nunca era exercido — a latência de rede dominava em demasia.

## Decisão

Paralelizar a coleta com `concurrent.futures.ThreadPoolExecutor`, compartilhando um único `ProviderClient` entre as threads. O cliente já tem `threading.Lock` interno, então o rate limit continua sendo **do conjunto**, não por thread.

**Configuração padrão**: `provider_max_workers: 4` em `config/settings.json`. Este valor:
- Acelera a coleta **5–6x** (medido: 10,43s → 1,88s para 40 símbolos)
- Respeita o orçamento de `2 req/s` — aí sim ele é ativado, em vez de nunca ser usado
- Não explora demais: Yahoo não documenta limite oficial, bloqueios por rate-limit vêm de uso abusivo

## Implementação

**Dois pontos de paralelismo agora:**

1. **`providers/yahoo.py::fetch_watchlist`** — coleta da carteira + watchlist
   - Parâmetro: `max_workers` (default 1, preserva comportamento antigo)
   - Chamado por: `application/collection.py::download_stage()`

2. **`universe/collector.py::collect_constituent_batch`** — coleta ampla por lote
   - Parâmetro: `max_workers` (default 1, regressão-safe)
   - Chamado por: `universe/collector.py::main()` com `max_workers=int(settings.get("provider_max_workers", 4))`

Ambos usam o mesmo padrão:
- `pending = [símbolos não coletados]`
- `state_lock = threading.Lock()` protege `observations`/`failures`/checkpoint
- `ThreadPoolExecutor(max_workers)` + `list(pool.map(processo, pending))`
- Ordem de saída determinística: `.update()` no `state` em índice, não na ordem de término

## Invariantes travadas

- **Ordem determinística**: Saída na ordem da entrada, não de término de thread
- **Rate limit global**: Intervalo mínimo entre chamadas respeita o orçamento (não por thread)
- **Nenhuma perda de observação**: Lock + write ao checkpoint protegem integridade
- **Falhas mantêm símbolo**: Associação `símbolo → erro` persiste
- **Sequencial segue funcionando**: Default `max_workers=1` roda como antes

## Consequências

- **Ganho medido**: ~5,5x de speedup em testes; coleta ampla de 901 restantes: ~60min → ~40-45min
- **Custo**: Carga real ao Yahoo aumenta de ~0,26 req/s para ~2 req/s (usa o orçamento que política já definia)
- **Risco**: Se Yahoo bloqueia em 429, baixar `provider_max_workers` para 2 em `settings.json`

## Próximas sessões

Padrão para coleta de produção é agora:
```bash
python atlas.py hoje                    # usa max_workers=4, ambos fetch_watchlist e universe collector
python -m universe.collector --market   # usa max_workers=4
```

Sem passar `max_workers`, pega a configuração de `settings.json`. Para testes/debug:
```python
# Força sequencial
from universe.collector import collect_constituent_batch
result = collect_constituent_batch(..., max_workers=1)
```

## Referências

- ADR-045: Persistência de valores derivados (`analysis_values_json`)
- `providers/contracts.py::ProviderClient._wait_for_rate_limit()`: Implementação do rate limit com lock
- `tests/test_parallel_collection.py`: Testes de invariantes (ordem, rate limit, falhas, integridade)
