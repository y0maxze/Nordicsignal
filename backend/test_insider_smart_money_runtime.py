import insider_smart_money_runtime as sm


def row(person, value, role="", day="2026-08-30"):
    return {
        "person": person,
        "transaction_type": "buy",
        "transaction_value": value,
        "display_transaction_value": value,
        "trade_date": day,
        "shares": value / 10,
        "price": 10,
        "role": role,
    }


def test_small_purchase_does_not_enter_smart_money():
    out = sm.enrich({"items": [row("Small Buyer", 36_000)]})
    q = out["insider_signal_v2"]["smart_money"]
    assert q["independent_qualified_actors"] == 0
    assert q["meaningful_actors_500k_plus"] == 0
    assert q["quality"] == "LOW"


def test_ceo_500k_is_meaningful_and_senior():
    out = sm.enrich({"items": [row("Chief Buyer", 500_000, "CEO")]})
    q = out["insider_signal_v2"]["smart_money"]
    assert q["independent_qualified_actors"] == 1
    assert q["meaningful_actors_500k_plus"] == 1
    assert q["senior_actors"] == 1
    assert q["role_adjusted_qualified_value_nok"] == 675_000


def test_repeated_same_actor_does_not_fake_independent_cluster():
    out = sm.enrich({"items": [
        row("Same Person", 300_000, "Board Member", "2026-08-29"),
        row("Same Person", 300_000, "Board Member", "2026-08-30"),
    ]})
    q = out["insider_signal_v2"]["smart_money"]
    assert q["independent_qualified_actors"] == 1
    assert q["meaningful_actors_500k_plus"] == 1
    assert q["repeated_same_actor_trades"] == 1


def test_multi_actor_meaningful_cluster_is_high_quality():
    out = sm.enrich({"items": [
        row("CEO Person", 800_000, "CEO"),
        row("Chair Person", 600_000, "Chair"),
        row("Board Person", 200_000, "Board Member"),
    ]})
    q = out["insider_signal_v2"]["smart_money"]
    assert q["independent_qualified_actors"] == 3
    assert q["meaningful_actors_500k_plus"] == 2
    assert q["senior_actors"] == 2
    assert q["quality"] == "HIGH"
    assert q["quality_points"] >= 5


def test_smart_money_never_changes_main_score_effect():
    out = sm.enrich({"items": [row("CEO Person", 2_000_000, "CEO")]})
    assert out["insider_signal_v2"]["score_effect"] == 0
    assert out["insider_signal_v2"]["smart_money"]["score_effect"] == 0
