"""Pure research accounting; no broker, database, feed or live-policy side effects.

Inputs must come from a reviewed adapter. Validation is not source certification.
One fully closed, unlevered NOK long position; dividends held as cash/receivables.
No portfolio return, tax, FX, dividend reinvestment or market-beating claim.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json

VERSION = 'research-round-trip-v1'
ZERO = Decimal('0')
ONE = Decimal('1')
BPS = Decimal('10000')


def amount(value, *, positive=False):
    if isinstance(value, bool) or value is None:
        raise ValueError('invalid_amount')
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError('invalid_amount') from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError('invalid_amount')
    if result > Decimal('1e15') or (result and result < Decimal('1e-12')):
        raise ValueError('amount_out_of_range')
    return result


def instant(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone_required')
    return parsed


def required(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + '_required')
    return value


def provenance(item, as_of):
    for key in ('source_ref', 'revision'):
        required(item.get(key), key)
    if instant(item['retrieved_at']) > as_of:
        raise ValueError('future_evidence')


def identity(item, isin):
    if item.get('isin') != isin or item.get('currency') != 'NOK':
        raise ValueError('identity_or_currency_mismatch')


def commission(notional, policy):
    minimum = amount(policy['minimum_nok'])
    rate = amount(policy['rate_bps'])
    if rate >= BPS:
        raise ValueError('invalid_commission_rate')
    return max(minimum, notional * rate / BPS).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def calculate(evidence):
    """Return reproducible before-tax research math, or reject incomplete inputs.

    Coverage is an adapter assertion, never inferred from an empty action list.
    An action at entry time is already reflected in the entry units; dividends
    are earned only for ex-times strictly after entry and at/before exit.
    """
    with localcontext() as ctx:
        ctx.prec = 40
        return _calculate(evidence)


def _calculate(e):
    as_of = instant(e['as_of'])
    isin = required(e.get('isin'), 'isin')
    entry, exit_ = e['entry'], e['exit']
    start, end = instant(entry['market_at']), instant(exit_['market_at'])
    if not instant(e['available_at']) < start < end <= as_of:
        raise ValueError('invalid_trade_period')
    for quote in (entry, exit_):
        identity(quote, isin)
        provenance(quote, as_of)
        if instant(quote['retrieved_at']) < instant(quote['market_at']):
            raise ValueError('price_retrieved_before_market')
        if quote.get('price_basis') != 'unadjusted' or quote.get('price_role') != 'reference':
            raise ValueError('unadjusted_reference_price_required')
    initial_units = amount(e['quantity'], positive=True)
    if initial_units != initial_units.to_integral_value():
        raise ValueError('whole_shares_required')
    units = initial_units
    coverage = e['action_coverage']
    identity(coverage, isin)
    provenance(coverage, as_of)
    if (coverage.get('complete') is not True or instant(coverage['from']) > start
            or instant(coverage['through']) < end
            or instant(coverage['retrieved_at']) < end):
        raise ValueError('corporate_action_coverage_missing')
    actions = e['actions']
    if not isinstance(actions, list) or len(actions) > 1000:
        raise ValueError('invalid_actions')
    seen, times, ordered = set(), set(), []
    for action in actions:
        identity(action, isin)
        provenance(action, as_of)
        key = required(action.get('id'), 'action_id')
        at = instant(action['effective_at'])
        if key in seen:
            raise ValueError('duplicate_action_or_revision')
        seen.add(key)
        if action.get('status') != 'confirmed':
            raise ValueError('unconfirmed_action')
        if not start <= at <= end:
            raise ValueError('action_outside_period')
        if at in times:
            raise ValueError('ambiguous_same_time_actions')
        times.add(at)
        if action['type'] not in ('split', 'cash_dividend'):
            raise ValueError('unsupported_corporate_action')
        ordered.append((at, action))
    paid, receivable = ZERO, ZERO
    for at, action in sorted(ordered, key=lambda x: x[0]):
        if action['type'] == 'split':
            ratio = amount(action['new_shares'], positive=True) / amount(action['old_shares'], positive=True)
            if at == start:
                continue
            units *= ratio
            if units != units.to_integral_value():
                raise ValueError('fractional_split_requires_cash_in_lieu')
        else:
            if action.get('amount_basis') != 'gross_per_share_at_ex':
                raise ValueError('dividend_basis_unknown')
            per_share = amount(action['amount'], positive=True)
            pay_at = instant(action['pay_at'])
            if pay_at < at:
                raise ValueError('payment_before_ex')
            if at == start:
                continue
            entitlement = units * per_share
            if pay_at <= end:
                paid += entitlement
            else:
                receivable += entitlement
    costs = e['cost_policy']
    provenance(costs, as_of)
    required(costs.get('version'), 'cost_version')
    if (costs.get('currency') != 'NOK' or instant(costs['fixed_at']) > instant(e['available_at'])
            or instant(costs['retrieved_at']) > instant(e['available_at'])):
        raise ValueError('cost_policy_not_fixed_before_signal')
    impacts = []
    for side in ('entry', 'exit'):
        policy = costs[side]
        impact = amount(policy['half_spread_bps']) + amount(policy['slippage_bps'])
        if impact >= BPS:
            raise ValueError('invalid_execution_impact')
        impacts.append(impact / BPS)
    raw_buy = amount(entry['price'], positive=True) * initial_units
    raw_sell = amount(exit_['price'], positive=True) * units
    buy = raw_buy * (ONE + impacts[0])
    sell = raw_sell * (ONE - impacts[1])
    buy_fee = commission(buy, costs['entry'])
    sell_fee = commission(sell, costs['exit'])
    invested = buy + buy_fee
    final_cash = sell - sell_fee + paid
    final_value = final_cash + receivable
    gross_return = (raw_sell + paid + receivable) / raw_buy - ONE
    net_return = final_value / invested - ONE
    benchmark = e['benchmark']
    provenance(benchmark, as_of)
    required(benchmark.get('id'), 'benchmark_id')
    if (benchmark.get('currency') != 'NOK' or benchmark.get('return_basis') != 'gross_total_return'
            or instant(benchmark['start_at']) != start or instant(benchmark['end_at']) != end
            or instant(benchmark['retrieved_at']) < end):
        raise ValueError('benchmark_not_comparable')
    benchmark_return = amount(benchmark['end_level'], positive=True) / amount(benchmark['start_level'], positive=True) - ONE
    digest = hashlib.sha256(json.dumps(e, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    values = {'initial_quantity': initial_units, 'final_quantity': units,
              'initial_outlay_nok': invested, 'exit_cash_nok': final_cash,
              'dividends_paid_nok': paid, 'dividends_receivable_nok': receivable,
              'end_value_nok': final_value, 'entry_commission_nok': buy_fee,
              'exit_commission_nok': sell_fee,
              'execution_impact_nok': buy - raw_buy + raw_sell - sell,
              'profit_nok': final_value - invested,
              'gross_return_pct': gross_return * 100, 'net_before_tax_return_pct': net_return * 100,
              'benchmark_return_pct': benchmark_return * 100,
              'difference_pp': (net_return - benchmark_return) * 100}
    return {'status': 'research_calculation', 'version': VERSION, 'evidence_hash': digest,
            'source_certified': False, 'dividends_reinvested': False, 'tax_included': False,
            'benchmark_is_investable_portfolio': False,
            'values': {k: format(v, 'f') for k, v in values.items()}}
