from insider_signal_v2_runtime import analyze


def test_cluster_buy_is_strong_and_transfer_is_excluded():
    result = analyze({
        "items": [
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "CEO", "role": "CEO", "shares": 37500, "price": 26.65},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "CFO", "role": "CFO", "shares": 8000, "price": 26.91},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "COO", "role": "COO", "shares": 4000, "price": 26.86},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "Board", "role": "Board member", "shares": 160000, "price": 26.75, "economic_exposure_unchanged": True},
        ]
    })
    signal = result["insider_signal_v2"]
    assert signal["label"] == "STRONG"
    assert signal["independent_buyers"] == 3
    assert signal["excluded_transfer_like_count"] == 1
    assert signal["buy_value_nok"] < 2_000_000
    assert signal["score_effect"] == 0


def test_single_small_buy_is_not_strong():
    signal = analyze({"items": [
        {"transaction_type": "buy", "trade_date": "2026-08-20", "actor": "Director", "shares": 100, "price": 20.0}
    ]})["insider_signal_v2"]
    assert signal["label"] == "MIXED"
    assert signal["points"] == 1


def test_net_selling_reduces_signal():
    signal = analyze({"items": [
        {"transaction_type": "buy", "trade_date": "2026-08-20", "actor": "CEO", "role": "CEO", "shares": 1000, "price": 20.0},
        {"transaction_type": "sell", "trade_date": "2026-08-20", "actor": "CFO", "role": "CFO", "shares": 5000, "price": 20.0},
    ]})["insider_signal_v2"]
    assert signal["points"] < 1
    assert signal["sell_value_nok"] > signal["buy_value_nok"]


def test_euronext_normalized_person_entity_direction_schema_is_supported():
    signal = analyze({"items": [
        {"direction": "buy", "trade_date": "2026-08-19", "person": "Sten Kirkbak", "role": "CEO", "shares": 37500, "price": 26.65},
        {"activity_type": "purchase", "trade_date": "2026-08-19", "person": "Knut Staalen", "role": "CFO", "shares": 8000, "price": 26.91},
        {"direction": "buy", "trade_date": "2026-08-20", "entity": "COO Holding AS", "related_primary_insider": "Jens Leth", "role": "COO", "shares": 4000, "price": 26.86},
    ]})["insider_signal_v2"]
    assert signal["label"] == "STRONG"
    assert signal["independent_buyers"] == 3
    assert signal["buy_count"] == 3


def test_xplra_like_real_cluster_counts_six_buyers_and_excludes_internal_transfer():
    items = [
        {"direction": "buy", "trade_date": "2026-08-19", "person": "Sten Kirkbak", "role": "CEO", "shares": 37500, "price": 26.65},
        {"direction": "buy", "trade_date": "2026-08-19", "person": "Knut Staalen", "role": "CFO", "shares": 8000, "price": 26.91},
        {"direction": "buy", "trade_date": "2026-08-20", "person": "Thomas Embla Bonnerud", "role": "Board member", "shares": 2250, "price": 26.75},
        {"direction": "buy", "trade_date": "2026-08-20", "person": "Jens Leth", "role": "COO", "shares": 4000, "price": 26.86},
        {"direction": "buy", "trade_date": "2026-08-20", "person": "Tomislav Krznaric", "role": "Business Unit Director", "shares": 4000, "price": 26.76},
        {"direction": "buy", "trade_date": "2026-08-20", "person": "Kristin Hellebust", "role": "CLO", "shares": 2950, "price": 27.0},
        {"direction": "buy", "trade_date": "2026-08-20", "person": "Kristin Hellebust", "role": "CLO", "shares": 2500, "price": 25.0},
        {"direction": "buy", "trade_date": "2026-08-20", "entity": "Cosimo AS", "related_primary_insider": "Trygve Bruland", "shares": 160000, "price": 26.75, "summary": "transfer to wholly owned company; no change in economic exposure", "economic_exposure_unchanged": True},
    ]
    signal = analyze({"items": items})["insider_signal_v2"]
    assert signal["label"] == "STRONG"
    assert signal["independent_buyers"] == 6
    assert signal["buy_count"] == 7
    assert signal["excluded_transfer_like_count"] == 1
    assert 1_600_000 <= signal["buy_value_nok"] <= 1_700_000


def test_duplicate_euronext_actor_variants_count_once():
    items = [
        {"direction": "buy", "trade_date": "2026-08-25", "actor": "Primary Insider Transaction Sjur Malm", "company": "Lerøy Seafood Group ASA", "shares": 1000, "price": 50.0, "node_id": "same-release"},
        {"direction": "buy", "trade_date": "2026-08-25", "person": "Sjur Malm", "company": "Lerøy Seafood Group ASA", "shares": 1000, "price": 50.0, "node_id": "same-release"},
    ]
    signal = analyze({"items": items})["insider_signal_v2"]
    assert signal["independent_buyers"] == 1
    assert signal["buy_count"] == 1
    assert signal["buy_value_nok"] == 50_000
    assert signal["deduplicated_row_count"] == 1


def test_raw_euronext_cluster_handles_correction_transfer_and_multi_leg_trade():
    company = "Xplora Technologies AS"
    items = [
        {"node_id":"12905672","published_at":"2026-08-20T14:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"shares":160000,"price":26.75,"transaction_value":4280000.0,"summary":"Cosimo AS, a company owned 100% by Trygve Bruland, who is a member of the board and primary insider of Xplora Technologies AS, bought on the 19 August 2026, 160,000 shares in the Company from Trygve Bruland personally at a price of NOK 26.75 per share."},
        {"node_id":"12905672","published_at":"2026-08-20T14:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"shares":2250,"price":26.75,"transaction_value":60187.5,"summary":"Thomas Embla Bonnerud, member of the board and primary insider of Xplora Technologies AS, bought 2,250 shares in the Company on 19 August 2026 at a price of NOK 26,75 per share."},
        {"node_id":"12905672","published_at":"2026-08-20T14:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"person":"Jens Leth","role":"COO","shares":4000,"price":26.86,"transaction_value":107440.0,"summary":"Jens Leth, COO and primary insider of Xplora Technologies AS, bought 4,000 shares in the Company on 19 August 2026 at a price of NOK 26,86 per share."},
        {"node_id":"12905672","published_at":"2026-08-20T14:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"shares":4000,"price":26.76,"transaction_value":107040.0,"summary":"Tomislav Krznari, Business Unit Director and primary insider of Xplora Technologies AS, bought 4,000 shares in the Company on 19 August 2026 at a price of NOK 26,76 per share."},
        {"node_id":"12905672","published_at":"2026-08-20T14:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"shares":2950,"price":27.0,"transaction_value":79650.0,"summary":"Kristin Hellebust, CLO and primary insider of Xplora Technologies AS, bought on the 19 August 2026 and 20 august 2026, respectively, 2,950 shares in the Company at a price of NOK 27 per share and 2,500 shares in the Company at a price of 25 NOK."},
        {"node_id":"12905416","published_at":"2026-08-19T16:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"person":"Sten Kirkbak","role":"CEO","shares":37500,"price":26.65,"transaction_value":999375.0,"summary":"Sten Kirkbak, CEO of Xplora Technologies AS and primary insider, bought 37,500 shares in the Company on 19 August 2026 through MK Capital AS at a price of NOK 26.65 per share."},
        {"node_id":"12905416","published_at":"2026-08-19T16:00:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"person":"and primary insider","role":"CFO","shares":8000,"price":26.91,"transaction_value":215280.0,"summary":"Knut Stålen, CFO and primary insider bought 8,000 shares in the Company on 19 August 2026 at an average price of NOK 26.91 per share."},
        {"node_id":"12905394","published_at":"2026-08-19T14:25:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"person":"Sten Kirkbak","role":"CEO","shares":37500,"price":26.65,"transaction_value":999375.0,"summary":"Sten Kirkbak, CEO of Xplora Technologies AS and primary insider, bought 37,500 shares in the Company on 19 August 2026 through MK Capital AS at a price of NOK 26.65 per share."},
        {"node_id":"12905394","published_at":"2026-08-19T14:25:00+00:00","trade_date":"2026-08-19","direction":"buy","company":company,"person":"and primary insider","role":"CFO","shares":8000,"price":26.91,"transaction_value":215280.0,"summary":"Knut Stålen, CFO and primary insider bought 8,000 shares in the Company on 19 August 2026 at an average price of NOK 26.91 per share."},
    ]
    signal = analyze({"items": items})["insider_signal_v2"]
    assert signal["label"] == "STRONG"
    assert signal["independent_buyers"] == 6
    assert signal["buy_count"] == 7
    assert signal["excluded_transfer_like_count"] == 1
    assert signal["deduplicated_row_count"] == 2
    assert signal["prepared_item_count"] == 10
    assert round(signal["buy_value_nok"], 2) == 1_631_472.50
