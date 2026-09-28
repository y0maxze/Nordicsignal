"""Stock-page reads. A missing ranking or failed cache write is not missing market data."""
import logging
from datetime import datetime, timezone

from scoring import signal_label

log = logging.getLogger(__name__)


def stock_summary(ticker, connect, issuer_lookup):
    ticker = str(ticker).strip().upper().removesuffix('.OL')
    conn = connect()
    try:
        row = conn.execute(
            'SELECT s.ticker,s.name,s.sector,s.exchange,sc.fundamentals,sc.insider,'
            'sc.valuation,sc.sentiment,sc.total,sc.created_at,sc.source FROM stocks s '
            'LEFT JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores WHERE ticker=s.ticker) '
            'WHERE s.ticker=?', (ticker,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        # Existing exact issuer reconciliation rejects ambiguous/reused tickers.
        # This only reads its snapshots; never enrol an issuer in the scoring universe.
        issuer = issuer_lookup().get(ticker)
        if not issuer:
            return {'error': 'Ticker not found'}
        row = {'ticker': ticker, 'name': issuer['company'], 'sector': issuer.get('sector')}
    row = dict(row)
    score = row.get('total')
    source = (row.get('source') or 'stored') if score is not None else 'unavailable'
    return {
        'ticker': ticker, 'name': row['name'], 'sector': row.get('sector'),
        'exchange': row.get('exchange'), 'score': score,
        'fundamentals': row.get('fundamentals'),
        'insider': row.get('insider') if source == 'live' else None,
        'valuation': row.get('valuation'), 'sentiment': row.get('sentiment'),
        'signal': signal_label(score) if score is not None else None,
        'score_source': source, 'live_verified': source == 'live',
        'partial_live': source == 'partial_live', 'score_updated_at': row.get('created_at'),
    }


def quote_result(ticker, provider, connect):
    ticker = str(ticker).strip().upper().removesuffix('.OL')
    try:
        data = dict(provider.quote(ticker))
    except Exception:
        return {'ticker': ticker, 'source': 'unavailable', 'status': 'unavailable'}
    conn = None
    try:
        conn = connect()
        if not conn.execute('SELECT ticker FROM stocks WHERE ticker=?', (ticker,)).fetchone():
            data['persistence_status'] = 'outside_scoring_universe'
        else:
            conn.execute(
                'INSERT INTO quotes(ticker,price,change_pct,volume,captured_at) VALUES(?,?,?,?,?)',
                (ticker, data.get('price'), data.get('change_pct'), data.get('volume'),
                 data.get('captured_at') or datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            data['persistence_status'] = 'stored'
    except Exception:
        # Provider evidence is still valid when the optional historical write fails.
        data['persistence_status'] = 'unavailable'
        log.warning('Quote history write unavailable for %s', ticker)
    finally:
        if conn is not None:
            conn.close()
    return data
