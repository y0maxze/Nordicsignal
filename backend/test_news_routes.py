from unittest.mock import MagicMock, patch

from fastapi import FastAPI

import news_routes
import pytest


@pytest.mark.parametrize('title,related,company', [
    ('Bio-Techne shareholders approve takeover', ['TECH'], 'TECH'),
    ('INCY or TECH: Which Is the Better Value Stock?', ['INCY', 'TECH'], 'Techstep ASA'),
    ('Techstep ASA quarterly results', ['TECH'], 'Techstep ASA'),
    ('TECH quarterly report', [], 'TECH'),
    ('Aker Carbon Capture results', [], 'Aker Solutions'),
    ('NotTechstep ASA results', [], 'Techstep ASA'),
])
def test_rejects_cross_exchange_and_partial_name_media(title, related, company):
    assert not news_routes.news_matches_ticker(
        {'title': title, 'relatedTickers': related}, 'TECH', company)


def test_exact_oslo_symbol_and_complete_untagged_name_are_supported():
    assert news_routes.news_matches_ticker({'relatedTickers': ['TECH.OL']}, 'tech.ol', 'TECH')
    assert news_routes.news_matches_ticker({'title': 'Techstep ASA: quarterly results'}, 'TECH', 'Techstep ASA')


def test_yahoo_fallback_qualifies_symbol_and_filters_before_report_classification():
    provider = MagicMock()
    provider.BASE = 'https://provider.test'
    provider._get.return_value = {'news': [
        {'title': 'Bio-Techne earnings report', 'relatedTickers': ['TECH']},
        {'title': 'Techstep quarterly results', 'relatedTickers': ['TECH.OL'], 'providerPublishTime': 1},
    ]}
    result = news_routes._yahoo_news(provider, 'TECH', 'TECH', 10)
    assert 'q=TECH.OL&' in provider._get.call_args.args[0]
    assert [x['title'] for x in result['items']] == ['Techstep quarterly results']
    assert result['items'][0]['category'] == 'Rapport'


def test_issuer_company_name_comes_from_stock_registry():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"name": "Lerøy Seafood"}
    with patch.object(news_routes, "connect", return_value=conn):
        assert news_routes._issuer_company_name("lsg") == "Lerøy Seafood"
    conn.execute.assert_called_once()
    conn.close.assert_called_once()


def test_issuer_company_name_falls_back_to_ticker_when_registry_unavailable():
    with patch.object(news_routes, "connect", side_effect=RuntimeError("db unavailable")):
        assert news_routes._issuer_company_name("LSG") == "LSG"


def test_reports_route_does_not_depend_on_retired_extra_api_company_helper():
    app = FastAPI()
    news_routes.install_routes(app)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/reports/{ticker}")
    aggregate = {
        "ticker": "LSG",
        "company": "Lerøy Seafood",
        "items": [{"title": "Lerøy Seafood Q2 report", "category": "Rapport"}],
        "source": "test",
        "sources": ["test"],
    }
    with patch.object(news_routes, "_issuer_company_name", return_value="Lerøy Seafood"), patch.object(
        news_routes, "aggregate_news", return_value=aggregate
    ):
        result = endpoint("LSG", 12)
    assert result["ticker"] == "LSG"
    assert result["company"] == "Lerøy Seafood"
    assert result["status"] == "live_reports"
    assert len(result["items"]) == 1
