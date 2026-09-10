"""Small observability endpoint for scored-universe coverage additions."""

import extra_api
from market_coverage_runtime import EXPANDED_UNIVERSE


def install():
    if getattr(extra_api, "_market_coverage_status_installed", False):
        return
    original = extra_api.install

    def install_with_status(app):
        result = original(app)

        @app.get("/api/market-coverage/status")
        def market_coverage_status():
            return {
                "status": "ok",
                "observed_gap_additions": [
                    {"ticker": ticker, "name": name, "sector": sector}
                    for ticker, name, sector in EXPANDED_UNIVERSE
                ],
                "policy": "coverage expansion only; no score or signal threshold changes",
                "institutional_flow_policy": "context only until reliable point-in-time ownership data and forward evidence exist",
            }

        return result

    extra_api.install = install_with_status
    extra_api._market_coverage_status_installed = True
