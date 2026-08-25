# NordicSignal backend

FastAPI service for NordicSignal market data, scoring, regulatory data, paper trading and backtesting.

## Storage

Production uses PostgreSQL when `DATABASE_URL` is set. SQLite is the local fallback.

Core tables include stocks, quotes, fundamentals, insider trades, short positions, scores and watchlist. Paper-trading tables are installed by the paper API layer.

## Providers

- Yahoo Finance: quotes, price history and fundamental timeseries
- Finanstilsynet Short Sale Register: public net short positions
- Euronext Oslo Børs / company IR sources: public company news, reports and primary-insider disclosures

Runtime enrichment modules add structured news, insider ownership, market-pressure alerts, paper history and other additive endpoints without preventing core API startup if an optional external source is unavailable.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Test

```bash
python -m compileall -q .
python -m unittest discover -p 'test_*.py' -v
```

Do not present inferred price/volume pressure as real Level 2 order-book data. Public regulatory values and original source links should remain traceable wherever possible.
