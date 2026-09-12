from pathlib import Path

import short_alert_runtime


ROOT = Path(__file__).resolve().parents[1]


class _Row(dict):
    pass


class _Connection:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.closed = False

    def execute(self, sql, params):
        assert 'SELECT name FROM stocks WHERE ticker=?' in sql
        assert params == ('LSG',)
        if self.error:
            raise self.error
        return self

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


def test_market_pressure_uses_canonical_stock_registry(monkeypatch):
    conn = _Connection(_Row(name='Lerøy Seafood Group ASA'))
    monkeypatch.setattr(short_alert_runtime, 'connect', lambda: conn)

    assert short_alert_runtime._issuer_company_name('lsg.ol') == 'Lerøy Seafood Group ASA'
    assert conn.closed is True


def test_market_pressure_falls_back_to_ticker_on_registry_error(monkeypatch):
    conn = _Connection(error=RuntimeError('db unavailable'))
    monkeypatch.setattr(short_alert_runtime, 'connect', lambda: conn)

    assert short_alert_runtime._issuer_company_name('lsg') == 'LSG'
    assert conn.closed is True


def test_market_pressure_does_not_call_removed_extra_api_company_helper():
    source = (ROOT / 'backend' / 'short_alert_runtime.py').read_text(encoding='utf-8')
    assert 'extra_api._company_name' not in source
    assert "company=_issuer_company_name(ticker)" in source
