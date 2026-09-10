"""Provider-free production API entrypoint.

The production module keeps the bounded refresh implementation and route guards,
but its deploy-time market warmup is replaced before ASGI startup fires. Scheduled
Cloudflare refreshes own provider-wide work; the API starts with database/schema work
only and serves the latest persisted data immediately.
"""
import logging

import production

app = production.app
log = logging.getLogger("nordicsignal.api_entrypoint")


def remove_retired_product_routes():
    """Remove retired user-facing Paper Trading / Backtest endpoints from production."""
    kept = []
    removed = []
    for route in app.router.routes:
        path = getattr(route, "path", "") or ""
        if path == "/api/paper" or path.startswith("/api/paper/"):
            removed.append(path)
            continue
        kept.append(route)
    app.router.routes[:] = kept
    if removed:
        log.info("Removed %d retired Paper Trading routes", len(removed))
    return removed


# Paper Trading and its product backtest were retired from NordicSignal. Filtering at
# the production entrypoint means the endpoints are absent from routing/OpenAPI rather
# than merely hidden in the frontend. Internal model-validation workflows are separate.
remove_retired_product_routes()


def api_startup():
    production.main.init_db()
    production.main.seed_db()
    production.ensure_indexes()
    log.info(
        "API startup is provider-free; scheduled refresh owns provider-wide market work (workers=%d)",
        production._PROVIDER_WORKERS,
    )


# Importing production registers its safer bounded refresh route behavior, but ASGI
# startup has not executed yet. Replace only the warmup startup handler; manual and
# scheduled /api/refresh still use production's bounded, authenticated refresh path.
try:
    app.router.on_startup.remove(production.production_startup)
except ValueError:
    pass
if api_startup not in app.router.on_startup:
    app.router.on_startup.append(api_startup)
