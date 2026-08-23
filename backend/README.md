# NordicSignal backend

The API now has a persistent SQLite database with tables for:
- stocks
- quotes
- fundamentals
- insider trades
- short positions
- scores
- watchlist

Run:
`pip install -r requirements.txt`
`uvicorn main:app --reload`

The real-time provider is intentionally left as an adapter until a licensed data source is selected.
