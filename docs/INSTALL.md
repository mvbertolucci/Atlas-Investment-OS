# Installation

## Requirements

- Python 3.11 or newer
- Windows, macOS or Linux
- Internet access for market data collection

## Windows installation

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Validate the installation

```cmd
pytest
```

## Run Atlas

```cmd
python run_all.py
```

## Local data

Atlas creates local runtime files:

```text
data/atlas_history.db
logs/atlas.log
logs/execution_metrics.csv
output/latest.xlsx
output/morning_brief.md
output/history/
```

They are intentionally ignored by Git.
