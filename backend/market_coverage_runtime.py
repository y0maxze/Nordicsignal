"""Expand scored coverage for verified blind spots without changing score policy.

DVD and AKER were observed in material public-market events while the fixed core
universe did not contain them. The market-wide insider collector could still see
DVD, but the stock was not seeded/refreshed/scored by the core engine. AKER had the
same universe problem for company/news analysis.

This runtime deliberately changes coverage only. It does not change component
weights, signal thresholds, Opportunity rules, High Conviction activation or
position sizing.
"""

import extra_api
import insider_runtime


EXPANDED_UNIVERSE = (
    ("DVD", "Deep Value Driller", "Energy Services"),
    ("AKER", "Aker ASA", "Industrials"),
)

ISSUER_ALIASES = {
    "DVD": ("Deep Value Driller AS", ("deep value driller", "deep value driller as")),
    "AKER": ("Aker ASA", ("aker asa",)),
}


def _register_issuer_aliases():
    insider_runtime.ISSUERS.update(ISSUER_ALIASES)


def _install_universe_startup(app):
    @app.on_event("startup")
    def _expand_observed_market_coverage():
        # main is fully initialized by the time startup handlers execute. This
        # handler is registered before main.startup, so seed_db/refresh_all see
        # the expanded list on the same boot.
        import main

        known = {row[0] for row in main.UNIVERSE}
        for row in EXPANDED_UNIVERSE:
            if row[0] not in known:
                main.UNIVERSE.append(row)
                known.add(row[0])
        main.TICKERS[:] = [row[0] for row in main.UNIVERSE]


def install():
    if getattr(extra_api, "_market_coverage_runtime_installed", False):
        return
    _register_issuer_aliases()
    original_install = extra_api.install

    def install_with_market_coverage(app):
        result = original_install(app)
        _install_universe_startup(app)
        return result

    extra_api.install = install_with_market_coverage
    extra_api._market_coverage_runtime_installed = True


install()
