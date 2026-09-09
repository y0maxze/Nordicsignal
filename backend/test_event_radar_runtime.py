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


def test_provider_work_happens_outside_cache_lock(monkeypatch):
    acquired=[]
    def fake_feed(provider=None,limit=50):
        ok=radar._CACHE_LOCK.acquire(timeout=0.1)
        acquired.append(ok)
        if ok:
            radar._CACHE_LOCK.release()
        return {"items":[]}
    monkeypatch.setattr(radar.general_news_runtime,"general_market_news",fake_feed)
    radar.build_event_radar(force=True,provider=object())
    assert acquired == [True]


def test_policy_keeps_radar_separate_from_score(monkeypatch):
    monkeypatch.setattr(radar.general_news_runtime,"general_market_news",lambda provider=None,limit=50:{"items":[]})
    result=radar.build_event_radar(force=True,provider=object())
    assert "Does not change NordicSignal scores" in result["policy"]
