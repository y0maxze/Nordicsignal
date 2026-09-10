import ipo_autoscan_runtime as autoscan


def test_scan_ipo_once_refreshes_radar_and_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(autoscan.ipo_radar_runtime, "build_ipo_radar", lambda force=False: calls.append(("radar", force)) or {"status": "ok", "count": 2})
    monkeypatch.setattr(autoscan.ipo_listing_registry_runtime, "sync_listings", lambda: calls.append(("registry", True)) or {"status": "ok"})
    monkeypatch.setattr(autoscan, "_registry_due", lambda: True)
    monkeypatch.setattr(autoscan, "_mark_registry_sync", lambda: None)
    monkeypatch.setattr(autoscan, "_write_state", lambda *args, **kwargs: None)
    result = autoscan.scan_ipo_once()
    assert result["status"] == "ok"
    assert result["candidate_count"] == 2
    assert result["registry_synced"] is True
    assert ("radar", True) in calls
    assert ("registry", True) in calls


def test_scan_ipo_once_skips_registry_when_not_due(monkeypatch):
    calls = []
    monkeypatch.setattr(autoscan.ipo_radar_runtime, "build_ipo_radar", lambda force=False: {"status": "ok", "count": 1})
    monkeypatch.setattr(autoscan.ipo_listing_registry_runtime, "sync_listings", lambda: calls.append("registry") or {"status": "ok"})
    monkeypatch.setattr(autoscan, "_registry_due", lambda: False)
    monkeypatch.setattr(autoscan, "_write_state", lambda *args, **kwargs: None)
    result = autoscan.scan_ipo_once()
    assert result["registry_synced"] is False
    assert calls == []


def test_scan_failure_is_additive_and_does_not_raise(monkeypatch):
    monkeypatch.setattr(autoscan.ipo_radar_runtime, "build_ipo_radar", lambda force=False: (_ for _ in ()).throw(RuntimeError("provider down")))
    monkeypatch.setattr(autoscan, "_registry_due", lambda: False)
    monkeypatch.setattr(autoscan, "_write_state", lambda *args, **kwargs: None)
    result = autoscan.scan_ipo_once()
    assert result["status"] == "unavailable"


def test_registry_sync_interval_is_six_hours():
    assert autoscan.REGISTRY_SYNC_INTERVAL_SECONDS == 21600
