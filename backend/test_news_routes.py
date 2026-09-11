from unittest.mock import MagicMock, patch

from fastapi import FastAPI

import news_routes


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
