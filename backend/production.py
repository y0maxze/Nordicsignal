"""Production entrypoint for NordicSignal.

The development ``main`` module keeps its eager refresh behaviour for backwards
compatibility. Render imports this module instead so the HTTP service becomes ready
immediately and expensive market refreshes warm in the background.
"""

import logging
import threading
import time

import main
from database import connect

log = logging.getLogger("nordicsignal.production")
app = main.app

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_scores_ticker_id ON scores(ticker,id)",
    "CREATE INDEX IF NOT EXISTS idx_scores_created_at ON scores(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_ticker_captured ON quotes(ticker,captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_holding_tx_account_date ON holding_transactions(broker,account_type,transaction_date,id)",
    "CREATE INDEX IF NOT EXISTS idx_holding_tx_ticker_type_date ON holding_transactions(ticker,transaction_type,transaction_date,id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_events_class_created ON signal_events(asset_class,created_at,id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_catalog_class_seen ON signal_instrument_catalog(asset_class,last_seen_at)",
)


def ensure_indexes():
    """Create performance indexes without making optional tables a startup blocker."""
    for statement in _INDEXES:
        conn = None
        try:
            conn = connect()
            conn.execute(statement)
            conn.commit()
        except Exception as exc:
            # Optional runtime tables may legitimately be unavailable if a module was
            # disabled. One missing index must never abort application startup.
            log.warning("Index setup skipped: %s", exc)
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass


def _market_warmup():
    """Warm public market data after the server is already accepting requests."""
    try:
        main.refresh_all(include_insider=False)
    except Exception:
        log.exception("Background market refresh failed")
    # Give the first dashboard requests priority before the slower regulatory pass.
    time.sleep(3)
    try:
        main.refresh_all(include_insider=True)
    except Exception:
        log.exception("Background insider refresh failed")


def production_startup():
    main.init_db()
    main.seed_db()
    ensure_indexes()
    threading.Thread(
        target=_market_warmup,
        daemon=True,
        name="nordicsignal-market-warmup",
    ).start()


# main.startup synchronously refreshed all 24 stocks before Uvicorn reported ready.
# Replace exactly that handler in production while leaving local/dev behaviour intact.
try:
    app.router.on_startup.remove(main.startup)
except ValueError:
    pass
if production_startup not in app.router.on_startup:
    app.add_event_handler("startup", production_startup)
