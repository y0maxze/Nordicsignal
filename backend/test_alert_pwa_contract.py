from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_alert_inbox_is_part_of_versioned_pwa_shell():
    sw = _read("frontend/sw.js")
    assert "CACHE_NAME='nordicsignal-shell-v4'" in sw
    for asset in (
        "'/alerts'",
        "'/alerts.js'",
        "'/alert_local_capture.js'",
        "'/alert_nav_ui.js'",
    ):
        assert asset in sw


def test_alert_routes_and_mobile_hooks_remain_wired():
    worker = _read("worker.js")
    assert '["/alerts", "/alerts.html"]' in worker
    assert '["/notifications", "/alerts.html"]' in worker
    assert '<script src="/alert_local_capture.js"></script>' in worker
    assert '<script src="/alert_nav_ui.js"></script>' in worker
