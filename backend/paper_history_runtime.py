"""Enriched paper-trading journal and closed-trade statistics."""


def enrich_history(trades):
    """Replay trades FIFO and attach realized P/L to sell executions.

    Input may be sqlite Row objects or dictionaries. Returned items are plain dicts
    in newest-first order, while FIFO accounting is performed oldest-first.
    """
    ordered = [dict(t) for t in trades]
    ordered.sort(key=lambda x: (x.get('id') or 0, x.get('executed_at') or ''))
    layers = {}
    enriched = []
    realized_total = 0.0
    fees_total = 0.0
    volume = 0.0
    winners = losers = breakeven = sells = 0
    sell_results = []

    for t in ordered:
        ticker = str(t.get('ticker') or '').upper()
        side = str(t.get('side') or '').lower()
        shares = float(t.get('shares') or 0)
        price = float(t.get('price') or 0)
        fee = float(t.get('fee') or 0)
        gross = shares * price
        fees_total += fee
        volume += gross
        item = dict(t)
        item.update({'gross': gross, 'realized_pnl': None, 'realized_pnl_pct': None, 'cost_basis_sold': None})

        if side == 'buy':
            layers.setdefault(ticker, []).append([shares, gross + fee])
            enriched.append(item)
            continue

        if side != 'sell':
            enriched.append(item)
            continue

        sells += 1
        remaining = shares
        removed_cost = 0.0
        queue = layers.setdefault(ticker, [])
        while remaining > 1e-10 and queue:
            layer_shares, layer_cost = queue[0]
            take = min(remaining, layer_shares)
            unit_cost = layer_cost / layer_shares if layer_shares else 0.0
            removed_cost += take * unit_cost
            layer_shares -= take
            layer_cost -= take * unit_cost
            remaining -= take
            if layer_shares <= 1e-10:
                queue.pop(0)
            else:
                queue[0] = [layer_shares, layer_cost]

        # API already prevents oversells. If legacy/corrupt rows contain one,
        # leave realized P/L unknown instead of inventing a cost basis.
        if remaining > 1e-8:
            item['accounting_status'] = 'insufficient_history'
            enriched.append(item)
            continue

        proceeds = gross - fee
        pnl = proceeds - removed_cost
        pct = pnl / removed_cost * 100 if removed_cost else None
        item.update({'cost_basis_sold': removed_cost, 'net_proceeds': proceeds, 'realized_pnl': pnl, 'realized_pnl_pct': pct, 'accounting_status': 'ok'})
        realized_total += pnl
        sell_results.append(item)
        if pnl > 1e-9:
            winners += 1
        elif pnl < -1e-9:
            losers += 1
        else:
            breakeven += 1
        enriched.append(item)

    valid_closed = winners + losers + breakeven
    best = max(sell_results, key=lambda x: x['realized_pnl'], default=None)
    worst = min(sell_results, key=lambda x: x['realized_pnl'], default=None)
    summary = {
        'trade_count': len(ordered),
        'buy_count': sum(1 for x in ordered if str(x.get('side') or '').lower() == 'buy'),
        'sell_count': sells,
        'closed_trade_count': valid_closed,
        'winners': winners,
        'losers': losers,
        'breakeven': breakeven,
        'win_rate': winners / valid_closed * 100 if valid_closed else None,
        'realized_pnl': realized_total,
        'fees_total': fees_total,
        'traded_volume': volume,
        'best_trade': best,
        'worst_trade': worst,
        'first_trade_at': ordered[0].get('executed_at') if ordered else None,
        'last_trade_at': ordered[-1].get('executed_at') if ordered else None,
    }
    return {'items': list(reversed(enriched)), 'summary': summary}


def install():
    try:
        import extra_api
        from database import connect
    except Exception:
        return
    if getattr(extra_api, '_paper_history_patch_v1', False):
        return
    original = extra_api.install

    def patched_install(app):
        original(app)

        @app.get('/api/paper/history')
        def paper_history(limit: int = 500, ticker: str | None = None):
            limit = min(max(int(limit), 1), 2000)
            conn = connect()
            try:
                # Replay all rows for correct FIFO cost basis, then filter output.
                rows = conn.execute('SELECT * FROM paper_trades WHERE account_id=1 ORDER BY id').fetchall()
            finally:
                conn.close()
            out = enrich_history(rows)
            if ticker:
                wanted = ticker.upper()
                out['items'] = [x for x in out['items'] if str(x.get('ticker') or '').upper() == wanted]
            out['items'] = out['items'][:limit]
            return out

        @app.get('/api/paper/dashboard')
        def paper_dashboard(limit: int = 100):
            conn = connect()
            try:
                rows = conn.execute('SELECT * FROM paper_trades WHERE account_id=1 ORDER BY id').fetchall()
            finally:
                conn.close()
            journal = enrich_history(rows)
            journal['items'] = journal['items'][:min(max(int(limit), 1), 500)]
            journal['portfolio'] = extra_api._positions(extra_api.YahooProvider())
            return journal

    extra_api.install = patched_install
    extra_api._paper_history_patch_v1 = True


install()
