# Atlas – Investment Decision OS

## Como rodar

Abra o Prompt de Comando dentro desta pasta e rode:

```cmd
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_all.py
```

O resultado será gerado em:

```text
output/latest.xlsx
output/history/
```

## Onde editar a watchlist

```text
config/watchlist.csv
```

## Onde mudar os pesos

```text
config/weights.json
```

## Onde mudar os deal breakers

```text
config/deal_breakers.json
```
