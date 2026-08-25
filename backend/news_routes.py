"""Canonical stock-news and report HTTP routes.

Aggregation/parsing lives in ``news_runtime``. This module is the single owner
of the public /api/news and /api/reports endpoints, so route behavior is no
longer split between extra_api and runtime replacement patches.
"""

from datetime import datetime, timezone
from urllib.parse import quote_plus

import extra_api
from news_runtime import aggregate_news
from providers import YahooProvider


def _yahoo_news(provider, ticker, company, limit):
    """Return strictly issuer-matched Yahoo items as the media fallback."""
    ticker = ticker.upper()
    limit = max(1, min(int(limit), 40))
    items = []
    try:
        query = f'{company} {ticker}' if company and company.upper() != ticker else ticker
        data = provider._get(
            f'{provider.BASE}/v1/finance/search?q={quote_plus(query)}&quotesCount=3&newsCount={min(limit * 4, 100)}'
        )
        for item in data.get('news') or []:
            related = [str(x).upper() for x in (item.get('relatedTickers') or [])]
            title = item.get('title') or ''
            normalized_title = title.lower()
            company_tokens = [
                x.lower() for x in (company or '').split()
                if len(x) >= 5 and x.lower() not in {'group', 'holding', 'international', 'systems', 'technologies', 'seafood'}
            ]
            matched = ticker in related or f'{ticker}.OL' in related
            if not matched and company:
                matched = company.lower() in normalized_title or any(token in normalized_title for token in company_tokens)
            if not matched:
                continue
            ts = item.get('providerPublishTime')
            low = normalized_title
            category = 'Nyhet'
            if any(k in low for k in ('insider', 'primary insider', 'mandatory notification')):
                category = 'Insider'
            elif any(k in low for k in ('report', 'results', 'quarter', 'q1', 'q2', 'q3', 'q4', 'earnings', 'annual report', 'interim report')):
                category = 'Rapport'
            elif any(k in low for k in ('dividend', 'ex-dividend', 'utbytte')):
                category = 'Utbytte'
            elif any(k in low for k in ('acqui', 'merger', 'contract', 'order', 'agreement')):
                category = 'Selskap'
            items.append({
                'ticker': ticker,
                'title': title,
                'publisher': item.get('publisher') or 'Unknown',
                'url': item.get('link') or '',
                'published_at': datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                'category': category,
                'summary': title,
                'related_tickers': item.get('relatedTickers') or [],
            })
            if len(items) >= limit:
                break
    except Exception as exc:
        return {'ticker': ticker, 'items': [], 'status': 'unavailable', 'source': 'Yahoo Finance search', 'error': str(exc)}
    return {
        'ticker': ticker,
        'company': company,
        'items': items,
        'status': 'live_news' if items else 'no_company_news',
        'source': 'Yahoo Finance search',
        'strict_issuer_filter': True,
    }


def install_routes(app):
    provider = YahooProvider()

    def base_news(ticker, limit=20):
        company = extra_api._company_name(ticker.upper())
        return _yahoo_news(provider, ticker, company, limit)

    @app.get('/api/news/{ticker}')
    def stock_news(ticker: str, limit: int = 20):
        ticker = ticker.upper()
        company = extra_api._company_name(ticker)
        return aggregate_news(base_news, ticker, company, limit)

    @app.get('/api/news/{ticker}/summary')
    def news_summary(ticker: str):
        data = stock_news(ticker, 8)
        items = data.get('items') or []
        counts = {}
        for item in items:
            category = item.get('category') or 'Nyhet'
            counts[category] = counts.get(category, 0) + 1
        return {
            'ticker': ticker.upper(),
            'headline_count': len(items),
            'categories': counts,
            'summary': ' · '.join(x.get('title') or '' for x in items[:3]) if items else 'Ingen nye offentlige nyheter funnet.',
            'items': items,
        }

    @app.get('/api/reports/{ticker}')
    def stock_reports(ticker: str, limit: int = 12):
        limit = max(1, min(int(limit), 30))
        data = stock_news(ticker, max(limit * 3, 20))
        items = [x for x in data.get('items') or [] if x.get('category') == 'Rapport'][:limit]
        return {
            'ticker': ticker.upper(),
            'company': data.get('company'),
            'items': items,
            'status': 'live_reports' if items else 'no_company_reports',
            'source': data.get('source'),
            'sources': data.get('sources'),
            'strict_issuer_filter': True,
        }


def install():
    """Attach canonical news/report routes to the existing feature chain."""
    if getattr(extra_api, '_canonical_news_routes_v1', False):
        return
    original = extra_api.install

    def patched_install(app):
        original(app)
        install_routes(app)

    extra_api.install = patched_install
    extra_api._canonical_news_routes_v1 = True


install()
