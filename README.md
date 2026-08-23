# NordicSignal

NordicSignal is a stock-intelligence dashboard designed around a 0–100 signal score.

## Current state
- Responsive dashboard
- Stock detail view
- Watchlist-ready UI
- Insider / short / valuation / fundamentals scoring model
- SQLite database schema
- FastAPI backend scaffold
- Provider abstraction for market-data integration
- Seed/demo data
- Real-time provider slot prepared

## Run locally
### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
Open `frontend/index.html` directly, or serve the folder with:
```bash
python -m http.server 8080 --directory frontend
```

Then visit http://localhost:8080.

## Important
Demo data is clearly marked in the UI. Before public launch, connect a licensed market-data provider and validate every data field, scoring rule, and redistribution right.
