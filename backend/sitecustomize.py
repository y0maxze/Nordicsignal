"""Runtime loader for NordicSignal optional integrations."""
import sys
import threading
import time


def _install_when_main_ready():
    for _ in range(200):
        try:
            main = sys.modules.get('main')
            app = getattr(main, 'app', None) if main else None
            if app is not None:
                from extra_api import install
                install(app)
                return
        except Exception:
            pass
        time.sleep(0.05)

try:
    from insider_runtime import install
    install()
except Exception:
    pass

threading.Thread(target=_install_when_main_ready, daemon=True, name='nordicsignal-extra-routes').start()
