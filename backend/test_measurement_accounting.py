from copy import deepcopy
from decimal import Decimal
import pytest
import measurement_accounting as accounting


def fixture():
    source = {'source_ref': 'fixture-only', 'revision': '1', 'retrieved_at': '2026-10-20T16:00:00Z'}
    security = {'isin': 'fixture-isin', 'currency': 'NOK'}
    start, end = '2026-10-12T07:00:00Z', '2026-10-20T14:25:00Z'
    costs = {'minimum_nok': '0', 'rate_bps': '0', 'half_spread_bps': '0', 'slippage_bps': '0'}
    return {'as_of': '2026-10-20T17:00:00Z', 'available_at': '2026-10-09T17:00:00Z',
            'isin': 'fixture-isin', 'quantity': '100',
            'entry': dict(source, **security, market_at=start, price='100', price_basis='unadjusted', price_role='reference'),
            'exit': dict(source, **security, market_at=end, price='110', price_basis='unadjusted', price_role='reference'),
            'action_coverage': dict(source, **security, complete=True, **{'from': start, 'through': end}),
            'actions': [],
            'cost_policy': dict(source, version='test-zero-cost', currency='NOK', fixed_at='2026-10-08T12:00:00Z',
                                retrieved_at='2026-10-08T12:00:00Z', entry=dict(costs), exit=dict(costs)),
            'benchmark': dict(source, id='fixture-gross-index', currency='NOK', return_basis='gross_total_return',
                              start_at=start, end_at=end, start_level='1000', end_level='1050')}


def action(kind, at='2026-10-15T07:00:00Z', **kwargs):
    return dict(id=kind, type=kind, isin='fixture-isin', currency='NOK', effective_at=at,
                source_ref='fixture-only', revision='1', retrieved_at='2026-10-20T16:00:00Z',
                status='confirmed', **kwargs)


def values(e):
    return {k: Decimal(v) for k, v in accounting.calculate(e)['values'].items()}


def test_no_side_effects_or_performance_claims():
    e=fixture(); original=deepcopy(e)
    r=accounting.calculate(e)
    assert e==original and r['status']=='research_calculation'
    assert r['source_certified'] is False and r['tax_included'] is False
    v=values(e)
    assert v['net_before_tax_return_pct']==10 and v['benchmark_return_pct']==5 and v['difference_pp']==5
    assert accounting.calculate(e)['evidence_hash']==r['evidence_hash']


@pytest.mark.parametrize('new,old,exit_price,final_units', [('2','1','50',200),('1','10','1000',10)])
def test_split_changes_units_without_creating_profit(new,old,exit_price,final_units):
    e=fixture();e['exit']['price']=exit_price
    e['actions']=[action('split',new_shares=new,old_shares=old)]
    v=values(e)
    assert v['final_quantity']==final_units and v['profit_nok']==0


def test_dividend_ex_drop_is_offset_without_double_counting():
    e=fixture();e['exit']['price']='95'
    e['actions']=[action('cash_dividend',amount='5',amount_basis='gross_per_share_at_ex',pay_at='2026-10-19T07:00:00Z')]
    v=values(e)
    assert v['dividends_paid_nok']==500 and v['profit_nok']==0


def test_unpaid_dividend_is_receivable_not_spendable_cash():
    e=fixture();e['exit']['price']='95'
    e['actions']=[action('cash_dividend',amount='5',amount_basis='gross_per_share_at_ex',pay_at='2026-10-25T07:00:00Z')]
    v=values(e)
    assert v['exit_cash_nok']==9500 and v['dividends_receivable_nok']==500 and v['profit_nok']==0


def test_purchase_on_ex_time_gets_no_dividend():
    e=fixture();e['actions']=[action('cash_dividend',at=e['entry']['market_at'],amount='5',amount_basis='gross_per_share_at_ex',pay_at='2026-10-19T07:00:00Z')]
    assert values(e)['dividends_paid_nok']==0


def test_sale_on_ex_time_keeps_dividend():
    e=fixture();e['actions']=[action('cash_dividend',at=e['exit']['market_at'],amount='5',amount_basis='gross_per_share_at_ex',pay_at='2026-10-25T07:00:00Z')]
    assert values(e)['dividends_receivable_nok']==500


def test_chronological_splits_and_dividends_preserve_entitlement_units():
    e=fixture();e['exit']['price']='50'
    dividend=action('cash_dividend',at='2026-10-16T07:00:00Z',amount='1',amount_basis='gross_per_share_at_ex',pay_at='2026-10-19T07:00:00Z')
    split=action('split',new_shares='2',old_shares='1')
    e['actions']=[dividend,split]
    assert values(e)['dividends_paid_nok']==200


def test_costs_on_both_sides_and_conservative_execution():
    e=fixture();e['exit']['price']='100'
    for side in ('entry','exit'):
        e['cost_policy'][side].update(minimum_nok='29',rate_bps='15',half_spread_bps='5',slippage_bps='5')
    v=values(e)
    assert v['initial_outlay_nok']==10039 and v['exit_cash_nok']==9961
    assert v['entry_commission_nok']==29 and v['exit_commission_nok']==29
    assert v['execution_impact_nok']==20 and v['profit_nok']==-78
    assert v['net_before_tax_return_pct']<0


def test_percentage_commission_and_rounding():
    assert accounting.commission(Decimal('100000'),{'minimum_nok':'29','rate_bps':'15'})==150
    assert accounting.commission(Decimal('10.05'),{'minimum_nok':'0','rate_bps':'100'})==Decimal('.10')


@pytest.mark.parametrize('value', [True,None,'NaN','Infinity','-1','0'])
def test_invalid_entry_price_rejected(value):
    e=fixture();e['entry']['price']=value
    with pytest.raises(ValueError): accounting.calculate(e)


@pytest.mark.parametrize('path,value,error', [
    (('entry','price_basis'),'adjusted','unadjusted_reference'),
    (('entry','price_role'),'execution','unadjusted_reference'),
    (('exit','currency'),'USD','identity'),
    (('exit','isin'),'wrong','identity'),
    (('exit','retrieved_at'),'2026-10-20T14:00:00Z','retrieved_before'),
    (('action_coverage','complete'),False,'coverage_missing'),
    (('action_coverage','through'),'2026-10-19T00:00:00Z','coverage_missing'),
    (('benchmark','start_at'),'2026-10-12T07:01:00Z','not_comparable'),
    (('benchmark','return_basis'),'price_return','not_comparable'),
    (('cost_policy','fixed_at'),'2026-10-10T00:00:00Z','not_fixed'),
    (('cost_policy','retrieved_at'),'2026-10-10T00:00:00Z','not_fixed'),
    (('exit','source_ref'),'','source_ref_required'),
    (('exit','retrieved_at'),'2026-10-21T00:00:00Z','future_evidence'),
    (('exit','market_at'),'2026-10-20T14:25:00','timezone_required'),
])
def test_incomplete_or_conflicting_inputs_fail_closed(path,value,error):
    e=fixture();e[path[0]][path[1]]=value
    with pytest.raises(ValueError,match=error): accounting.calculate(e)


def test_missing_costs_not_assumed_zero():
    e=fixture();del e['cost_policy']['entry']['slippage_bps']
    with pytest.raises(KeyError): accounting.calculate(e)


def test_duplicate_revisions_and_unsupported_actions_are_not_ignored():
    e=fixture();a=action('split',new_shares='2',old_shares='1');e['actions']=[a,dict(a,revision='2')]
    with pytest.raises(ValueError,match='duplicate'): accounting.calculate(e)
    e['actions']=[action('rights_issue')]
    with pytest.raises(ValueError,match='unsupported'): accounting.calculate(e)


def test_fractional_reverse_split_requires_explicit_cash_in_lieu():
    e=fixture();e['quantity']='101';e['actions']=[action('split',new_shares='1',old_shares='10')]
    with pytest.raises(ValueError,match='cash_in_lieu'): accounting.calculate(e)


def test_ambiguous_action_order_rejected():
    e=fixture();e['actions']=[action('split',new_shares='2',old_shares='1'),action('cash_dividend',amount='5')]
    with pytest.raises(ValueError,match='same_time'): accounting.calculate(e)


def test_timezone_equivalence_and_no_lookahead_entry():
    e=fixture();e['benchmark']['start_at']='2026-10-12T09:00:00+02:00'
    assert values(e)['difference_pp']==5
    e['available_at']=e['entry']['market_at']
    with pytest.raises(ValueError,match='trade_period'): accounting.calculate(e)
