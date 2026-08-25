"""FIFO realized gain/loss analytics for taxable share accounts.

ASK remains account-level and is intentionally excluded. This module enriches the
holdings snapshot without changing the transaction ledger or current positions.
"""
from collections import defaultdict, deque
from datetime import date

import holdings_routes

SHARE_TAX_RATE_2026 = 0.3784
TAXABLE_ACCOUNT_NAMES = {
    'aksje- og fondskonto', 'aksje og fondskonto', 'af', 'af-konto',
    'aksjekonto', 'vps', 'vps-konto',
}


def _norm(value):
    return ' '.join(str(value or '').strip().lower().split())


def _is_taxable_share_account(account_type):
    return _norm(account_type) in TAXABLE_ACCOUNT_NAMES


def fifo_realized_analysis(transactions, year=None):
    """Calculate FIFO realized P/L from ledger buys/sells for taxable accounts.

    Lots are isolated by broker + account type + ticker. ASK and unsupported account
    types are excluded. Oversells are flagged rather than assigned invented cost basis.
    """
    year = int(year or date.today().year)
    lots = defaultdict(deque)
    realized = []
    warnings = []
    ordered = sorted(
        transactions or [],
        key=lambda x: (str(x.get('transaction_date') or ''), int(x.get('id') or 0)),
    )
    for tx in ordered:
        account = tx.get('account_type')
        if not _is_taxable_share_account(account):
            continue
        kind = _norm(tx.get('transaction_type'))
        if kind not in {'buy', 'sell'}:
            continue
        ticker = str(tx.get('ticker') or '').strip().upper()
        shares = float(tx.get('shares') or 0)
        amount = float(tx.get('amount') or 0)
        price = float(tx.get('price') or 0)
        if not ticker or shares <= 0:
            warnings.append({'transaction_id': tx.get('id'), 'reason': 'missing_ticker_or_shares'})
            continue
        unit_price = price if price > 0 else (amount / shares if amount > 0 else 0)
        if unit_price <= 0:
            warnings.append({'transaction_id': tx.get('id'), 'reason': 'missing_price_or_amount'})
            continue
        key = (_norm(tx.get('broker')), _norm(account), ticker)
        if kind == 'buy':
            lots[key].append({'shares': shares, 'unit_cost': unit_price, 'transaction_id': tx.get('id')})
            continue

        remaining = shares
        cost_basis = 0.0
        matched = 0.0
        while remaining > 1e-12 and lots[key]:
            lot = lots[key][0]
            take = min(remaining, lot['shares'])
            cost_basis += take * lot['unit_cost']
            matched += take
            lot['shares'] -= take
            remaining -= take
            if lot['shares'] <= 1e-12:
                lots[key].popleft()
        if remaining > 1e-9:
            warnings.append({
                'transaction_id': tx.get('id'), 'ticker': ticker,
                'reason': 'sell_exceeds_recorded_fifo_lots', 'unmatched_shares': remaining,
            })
        if matched <= 0:
            continue
        proceeds = matched * unit_price
        gain_loss = proceeds - cost_basis
        tx_year = int(str(tx.get('transaction_date') or '0000')[:4] or 0)
        realized.append({
            'transaction_id': tx.get('id'), 'date': tx.get('transaction_date'),
            'year': tx_year, 'broker': tx.get('broker'), 'account_type': account,
            'ticker': ticker, 'shares_sold': matched, 'sale_price': unit_price,
            'proceeds': proceeds, 'cost_basis': cost_basis, 'realized_gain_loss': gain_loss,
        })

    year_rows = [x for x in realized if x['year'] == year]
    gains = sum(max(0.0, x['realized_gain_loss']) for x in year_rows)
    losses = sum(max(0.0, -x['realized_gain_loss']) for x in year_rows)
    net = gains - losses
    estimated_tax_effect = net * SHARE_TAX_RATE_2026
    remaining_lots = []
    for (broker, account, ticker), queue in lots.items():
        shares_left = sum(x['shares'] for x in queue)
        basis_left = sum(x['shares'] * x['unit_cost'] for x in queue)
        if shares_left > 1e-12:
            remaining_lots.append({
                'broker': broker, 'account_type': account, 'ticker': ticker,
                'shares': shares_left, 'cost_basis': basis_left,
                'average_fifo_cost': basis_left / shares_left,
            })
    return {
        'year': year,
        'method': 'FIFO',
        'tax_rate': SHARE_TAX_RATE_2026,
        'realized_trades': realized,
        'year_realized_trades': year_rows,
        'realized_gains': gains,
        'realized_losses': losses,
        'net_realized_gain_loss': net,
        'estimated_tax_effect': estimated_tax_effect,
        'estimated_tax_payable': max(0.0, estimated_tax_effect),
        'estimated_loss_tax_value': max(0.0, -estimated_tax_effect),
        'remaining_fifo_lots': remaining_lots,
        'warnings': warnings,
        'note': (
            'Estimat for vanlige skattepliktige aksjekontoer basert på registrerte kjøp/salg og FIFO. '
            'ASK er ekskludert. Skjerming, kurtasje som ikke ligger i registrert beløp/kostpris, valuta, '
            'corporate actions og andre individuelle skatteforhold kan endre faktisk skatt.'
        ),
    }


_original_snapshot = holdings_routes.build_holdings_snapshot


def build_holdings_snapshot_with_tax(provider=None):
    snapshot = _original_snapshot(provider)
    snapshot['realized_tax'] = fifo_realized_analysis(snapshot.get('transactions') or [])
    return snapshot


def install():
    if getattr(holdings_routes, '_fifo_tax_runtime_installed', False):
        return
    holdings_routes.build_holdings_snapshot = build_holdings_snapshot_with_tax
    holdings_routes._fifo_tax_runtime_installed = True
