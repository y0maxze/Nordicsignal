import event_radar_runtime as radar


def test_contract_classification():
    item={"title":"KOG: awarded contract valued at NOK 2 billion","official":True,"source_type":"exchange"}
    out=radar._event(item)
    assert out["event_type"] == "contract"
    assert out["verified"] is True


def test_lost_contract_has_priority_over_generic_contract():
    item={"title":"Company: contract terminated by customer","official":True,"source_type":"exchange"}
    assert radar._event(item)["event_type"] == "contract_lost"


def test_major_shareholding_classification():
    item={"title":"Notification of major shareholding","official":True,"source_type":"exchange"}
    assert radar._event(item)["event_type"] == "major_shareholding"


def test_irrelevant_release_is_not_promoted():
    assert radar._event({"title":"Invitation to presentation"}) is None


def test_extracts_nok_amount_with_norwegian_and_english_scales():
    assert radar._extract_nok_amount({"title":"Contract valued at NOK 2 billion"}) == 2_000_000_000
    assert radar._extract_nok_amount({"title":"Kontrakt på 750 mill NOK"}) == 750_000_000


def test_materiality_is_measured_against_revenue_only_when_evidence_exists():
    class Provider:
        def research(self,ticker): return {"financialData":{"totalRevenue":10_000_000_000}}
    event={"ticker":"KOG","event_type":"contract","title":"Awarded contract valued at NOK 2 billion"}
    out=radar._materiality(event,provider=Provider())
    assert out["status"] == "measured"
    assert out["revenue_ratio_pct"] == 20.0
    assert out["label"] == "Stor relativt til omsetning"


def test_materiality_fails_closed_when_amount_or_revenue_is_missing():
    class Provider:
        def research(self,ticker): return {"financialData":{"totalRevenue":None}}
    assert radar._materiality({"ticker":"KOG","event_type":"contract","title":"New contract"},provider=Provider())["status"] == "unknown"
    assert radar._materiality({"ticker":"KOG","event_type":"contract","title":"NOK 2 billion contract"},provider=Provider())["status"] == "unknown"


def test_materiality_does_not_change_event_priority():
    class Provider:
        def research(self,ticker): return {"financialData":{"totalRevenue":1_000_000_000}}
    event=radar._event({"ticker":"KOG","title":"Awarded contract valued at NOK 2 billion","official":True,"source_type":"exchange"})
    enriched=radar.enrich_materiality(event,provider=Provider())
    assert enriched["priority"] == "watch"
    assert enriched["materiality"]["revenue_ratio_pct"] == 200.0


def test_provider_work_happens_outside_cache_lock(monkeypatch):
    acquired=[]
    def fake_feed(provider=None,limit=50):
        ok=radar._CACHE_LOCK.acquire(timeout=0.1); acquired.append(ok)
        if ok: radar._CACHE_LOCK.release()
        return {"items":[]}
    monkeypatch.setattr(radar.general_news_runtime,"general_market_news",fake_feed)
    radar.build_event_radar(force=True,provider=object())
    assert acquired == [True]


def test_policy_keeps_radar_separate_from_score(monkeypatch):
    monkeypatch.setattr(radar.general_news_runtime,"general_market_news",lambda provider=None,limit=50:{"items":[]})
    result=radar.build_event_radar(force=True,provider=object())
    assert "Does not change NordicSignal scores" in result["policy"]
