# Portfolio CSV Specification

## File

```text
config/portfolio.csv
```

## Required columns

```csv
symbol,quantity,average_price
```

## Optional columns

```csv
currency,sector,country,notes
```

## Example

```csv
symbol,quantity,average_price,currency,sector,country,notes
MSFT,10,410.50,USD,Technology,USA,Core holding
GOOGL,8,175.20,USD,Communication Services,USA,
BUD,20,58.10,USD,Consumer Defensive,Belgium,
```

## Validation rules

- symbol is required
- quantity must be greater than zero
- average_price must be zero or greater
- duplicate symbols are merged
- invalid rows are reported
- unknown current price creates a warning
