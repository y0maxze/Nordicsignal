"""Bounded background enrichment on existing authenticated scheduler wakeups."""
import logging
import re
import threading
import extra_api
import ipo_autoscan_runtime as autoscan
import company_context as context
from fastapi import HTTPException

log=logging.getLogger(__name__)
_guard=threading.Lock()


def enqueue():
    if not _guard.acquire(blocking=False):return
    def run():
        try:
            context.scan_once()
            from company_newsweb import scan as scan_newsweb
            scan_newsweb(context.connect,context.universe(),context.now())
            from financing_documents import enrich_saved
            enrich_saved(context.connect, context.now())
        except Exception:log.exception('Company context background batch failed')
        finally:_guard.release()
    threading.Thread(target=run,name='company-context',daemon=True).start()


def install():
    if getattr(extra_api,'_company_context_v1',False):return
    context.ensure_schema()
    previous_scan=autoscan.scan_ipo_once
    def scan(*args,**kwargs):
        result=previous_scan(*args,**kwargs)
        enqueue()
        return result
    autoscan.scan_ipo_once=scan
    previous_install=extra_api.install
    def patched(app):
        previous_install(app)
        @app.get('/api/company-context/{ticker}')
        def company_context(ticker: str, before: str = None):
            ticker=ticker.upper().removesuffix('.OL')
            if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}',ticker):raise HTTPException(400,'Invalid ticker')
            row=context.universe().get(ticker)
            if not row:raise HTTPException(404,'Issuer identity unavailable')
            try:return context.context(ticker,identity=row['company'],before=before)
            except ValueError:raise HTTPException(400,'Invalid document cursor')
        @app.get('/api/company-context/{ticker}/evidence')
        def company_evidence(ticker: str, entity_key: str, revision: int):
            ticker=ticker.upper().removesuffix('.OL')
            if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}',ticker) or len(entity_key)>2048 or revision<1:
                raise HTTPException(400,'Invalid evidence reference')
            row=context.universe().get(ticker)
            if not row:raise HTTPException(404,'Issuer identity unavailable')
            from company_evidence import version
            data=version(context.connect,ticker,row['identity'],entity_key,revision)
            if not data:raise HTTPException(404,'Evidence version unavailable')
            return data
    extra_api.install=patched
    extra_api._company_context_v1=True


install()
