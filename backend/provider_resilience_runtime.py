"""Resilience patch for Yahoo market-data hosts.

Yahoo exposes equivalent query1/query2 hosts. Core quote/history callers previously
used only the primary host, so a transient host-specific failure could make the app
look offline even while the alternate endpoint was healthy.
"""

from providers import YahooProvider


def install():
    if getattr(YahooProvider, "_dual_host_failover_installed", False):
        return

    original_get = YahooProvider._get

    def resilient_get(self, url, params=None, need_crumb=False):
        candidates = [url]
        for base in self.BASES:
            if url.startswith(base):
                suffix = url[len(base):]
                candidates = [url] + [other + suffix for other in self.BASES if other != base]
                break

        last_error = None
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return original_get(self, candidate, params=params, need_crumb=need_crumb)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Yahoo endpoints unavailable: {last_error}")

    YahooProvider._get = resilient_get
    YahooProvider._dual_host_failover_installed = True
