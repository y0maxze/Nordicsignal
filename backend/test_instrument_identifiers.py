import hashlib
import sqlite3
import pytest
from instrument_identifiers import valid_isin, listing_identity
import ipo_listing_registry_runtime as registry


@pytest.mark.parametrize('isin',['NO0012885252','US0378331005','BE0003816338','CY0201461213'])
def test_known_identifiers_pass_syntax_and_check_digit(isin):
    assert valid_isin(isin)


@pytest.mark.parametrize('isin',[None,False,123,'','NO001288525','NO0012885253',
    'NO001288525A','no0012885252','NO 0012885252','NØ0012885252'])
def test_malformed_identifiers_are_not_silently_corrected(isin):
    assert not valid_isin(isin)
    projected = listing_identity({'isin':isin})
    assert projected['isin'] is None
    assert projected['reported_isin'] == isin


def test_bad_official_source_is_quarantined_without_rekeying_or_losing_evidence(tmp_path,monkeypatch):
    def connect():
        c=sqlite3.connect(tmp_path/'listing.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(registry,'connect',connect)
    raw='NO001288525'
    html=f'<table><tr><td>28/04/2023</td><td>NORSE ATLANTIC</td><td>NORSE</td><td>{raw}</td><td>Oslo</td><td>Euronext Expand</td></tr></table>'
    item=registry.parse_ipo_table(html)[0]
    expected=hashlib.sha256(f'2023-04-28|{raw}|NORSE ATLANTIC'.encode()).hexdigest()[:32]
    assert item['listing_id']==expected
    assert item['isin'] is None and item['reported_isin']==raw and item['isin_status']=='invalid'
    assert registry.record_listings([item])==1
    assert registry.record_listings([item])==0
    with connect() as c:
        assert c.execute('SELECT isin FROM ipo_listings').fetchone()['isin']==raw
    assert registry.listings()[0]['isin'] is None
    assert registry.listings()[0]['reported_isin']==raw


def test_checksum_validation_does_not_claim_current_identity():
    assert listing_identity({'isin':'NO0012885252'})['isin_status']=='format_valid'
