import ipo_listing_registry_runtime as registry
import ipo_evidence_runtime as evidence


def test_parse_official_euronext_ipo_table_rows():
    html = '''
    <table><thead><tr><th>Date</th><th>Company name</th><th>Ticker</th><th>ISIN code</th><th>Location</th><th>Market</th></tr></thead>
    <tbody>
      <tr><td>28/08/2026</td><td>OMC Tankers Ltd.</td><td>OMC</td><td>NO0013759159</td><td>Oslo</td><td>Euronext Growth</td></tr>
      <tr><td>18/06/2026</td><td>BOHUS</td><td>BOHUS</td><td>NO0013753343</td><td>Oslo</td><td>Euronext Oslo Børs</td></tr>
      <tr><td>01/07/2026</td><td>Other</td><td>OTH</td><td>XX1</td><td>Paris</td><td>Euronext Growth</td></tr>
    </tbody></table>'''
    rows = registry.parse_ipo_table(html)
    assert len(rows) == 2
    assert rows[0]["listing_date"] == "2026-08-28"
    assert rows[0]["ticker"] == "OMC"
    assert rows[0]["official"] is True
    assert rows[1]["market"] == "Euronext Oslo Børs"
    assert len(rows[0]["listing_id"]) == 32


def test_parser_dedupes_same_listing():
    row = '<tr><td>28/08/2026</td><td>OMC Tankers Ltd.</td><td>OMC</td><td>NO0013759159</td><td>Oslo</td><td>Euronext Growth</td></tr>'
    rows = registry.parse_ipo_table(f'<table>{row}{row}</table>')
    assert len(rows) == 1


def test_measure_uses_trading_rows_not_calendar_days():
    rows = [
        {"date": "2026-06-18", "close": 100.0},
        {"date": "2026-06-19", "close": 103.0},
        {"date": "2026-06-22", "close": 102.0},
        {"date": "2026-06-23", "close": 108.0},
    ]
    measured = evidence._measure(rows, 0, 2)
    assert measured["exit_date"] == "2026-06-22"
    assert round(measured["return_pct"], 3) == 2.0
    assert round(measured["max_runup_pct"], 3) == 3.0
    assert round(measured["max_drawdown_pct"], 3) == 0.0


def test_measure_requires_mature_horizon():
    rows = [{"date": "2026-06-18", "close": 100.0}, {"date": "2026-06-19", "close": 101.0}]
    assert evidence._measure(rows, 0, 5) is None


def test_benchmark_return_uses_same_trading_horizon():
    rows = [
        {"date": "2026-06-18", "close": 1000.0},
        {"date": "2026-06-19", "close": 1010.0},
        {"date": "2026-06-22", "close": 1020.0},
    ]
    result = evidence._benchmark_measure(rows, "2026-06-18", 2)
    assert round(result, 3) == 2.0


def test_offer_price_return_is_separate_from_close_to_close():
    first_day = evidence._return(80.0, 100.0)
    close_to_close = evidence._return(100.0, 105.0)
    assert round(first_day, 3) == 25.0
    assert round(close_to_close, 3) == 5.0


def test_fixed_maturity_policy():
    assert evidence._maturity(19) == "insufficient"
    assert evidence._maturity(20) == "early"
    assert evidence._maturity(49) == "early"
    assert evidence._maturity(50) == "useful_history"
