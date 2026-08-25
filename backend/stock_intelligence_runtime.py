from datetime import datetime, timezone


def classify_news_title(title):
    """Compatibility helper retained for callers/tests; routes live in news_routes."""
    low = (title or '').lower()
    if any(k in low for k in ('insider', 'primary insider', 'mandatory notification', 'meldepliktig')):
        return 'Insider'
    if any(k in low for k in ('report', 'results', 'quarter', 'q1', 'q2', 'q3', 'q4', 'earnings', 'årsrapport', 'annual report', 'interim report')):
        return 'Rapport'
    if any(k in low for k in ('dividend', 'ex-dividend', 'utbytte', 'distribution')):
        return 'Utbytte'
    if any(k in low for k in ('acqui', 'merger', 'contract', 'order', 'agreement', 'avtale', 'kontrakt')):
        return 'Selskap'
    return 'Nyhet'


def install():
    try:
        import extra_api
        from dividend_runtime import fetch_dividend_events
    except Exception:
        return
    if getattr(extra_api, '_stock_intelligence_patch_v2', False):
        return

    original = extra_api.install

    def patched_install(app):
        original(app)
        provider = extra_api.YahooProvider()

        @app.get('/api/dividends/{ticker}')
        def dividends(ticker: str, years: int = 10):
            ticker = ticker.upper()
            years = max(1, min(years, 25))
            now = datetime.now(timezone.utc)
            start = int(now.timestamp()) - int(years * 365.25 * 86400)
            end = int(now.timestamp()) + 86400
            try:
                items = fetch_dividend_events(provider, ticker, start, end)
            except Exception as exc:
                return {
                    'ticker': ticker,
                    'items': [],
                    'status': 'unavailable',
                    'source': 'Yahoo Finance chart events',
                    'error': str(exc),
                }
            total = sum(float(x.get('amount') or 0) for x in items)
            latest = items[-1] if items else None
            return {
                'ticker': ticker,
                'items': list(reversed(items)),
                'status': 'live_dividends' if items else 'no_dividends',
                'source': 'Yahoo Finance chart events',
                'event_count': len(items),
                'total_per_share': total,
                'latest': latest,
            }

        @app.get('/api/intelligence/{ticker}')
        def intelligence(ticker: str):
            """Aggregate endpoint for non-news stock intelligence."""
            ticker = ticker.upper()
            return {'ticker': ticker, 'dividends': dividends(ticker, 10)}

    extra_api.install = patched_install
    extra_api._stock_intelligence_patch_v2 = True


install()
