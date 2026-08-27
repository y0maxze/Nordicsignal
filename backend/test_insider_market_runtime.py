import unittest
from unittest.mock import patch

import general_news_runtime as gn
import insider_market_runtime as im
import insider_market_v2_runtime as im2


class InsiderMarketRuntimeTests(unittest.TestCase):
    def test_cluster_buying_is_prioritized(self):
        items = [
            {"ticker":"XPLRA","company":"Xplora Technologies","trade_date":"2026-08-20","direction":"buy","signal_eligible":True,"person":"CEO One","shares":1000,"display_value":500000,"currency":"NOK","activity_type":"share_purchase"},
            {"ticker":"XPLRA","company":"Xplora Technologies","trade_date":"2026-08-20","direction":"buy","signal_eligible":True,"person":"CFO Two","shares":2000,"display_value":1100000,"currency":"NOK","activity_type":"share_purchase"},
        ]
        pulse = im._pulse_groups(items)[0]
        self.assertEqual(pulse["signal_label"], "KLYNGEKJØP")
        self.assertEqual(pulse["unique_buyers"], 2)
        self.assertIn("cluster_buying", pulse["flags"])
        self.assertIn("large_buy", pulse["flags"])

    def test_large_single_purchase_is_visible(self):
        items = [{"ticker":"STECH","company":"Soiltech","trade_date":"2026-08-26","direction":"buy","signal_eligible":True,"entity":"Riverborg B.V.","shares":50008,"display_value":4000640,"currency":"NOK","activity_type":"share_purchase"}]
        pulse = im._pulse_groups(items)[0]
        self.assertEqual(pulse["signal_label"], "STORT KJØP")
        self.assertIn("large_buy", pulse["flags"])

    def test_non_trade_mechanics_are_not_signals(self):
        for text, expected in [
            ("Primary insider transferred shares from his personal account to holding company", "internal_transfer"),
            ("Primary insider was granted subscription rights and options", "rights_or_derivatives"),
            ("Purchase under employee share purchase programme", "employee_program"),
        ]:
            kind, eligible = im._activity_type(text, {"direction":"buy"})
            self.assertEqual(kind, expected)
            self.assertFalse(eligible)

    def test_ordinary_buy_remains_signal_eligible(self):
        kind, eligible = im._activity_type("The CFO purchased 10,000 shares at NOK 50 per share", {"direction":"buy"})
        self.assertEqual(kind, "share_purchase")
        self.assertTrue(eligible)

    def test_mixed_release_classifies_each_trade_segment(self):
        rows = [
            {"direction":"buy","transaction_type":"buy","shares":500000,"price":None,"summary":"Primary insider transferred shares from personal account to holding company"},
            {"direction":"buy","transaction_type":"buy","shares":25699,"price":0.35,"transaction_value":8994.65,"summary":"Primary insider purchased 25,699 shares at NOK 0.35 per share in the market"},
        ]
        item = {"ticker":"ACED","title":"ACED: Mandatory notification of trade","url":"https://example.test/release","published_at":"2026-08-26T10:00:00+00:00"}
        html = "<html><body>Primary insider mandatory notification of trade</body></html>"
        with patch.object(im.news_runtime, "_fetch_text", return_value=html), patch.object(im.insider_runtime, "parse_trades", return_value=rows):
            out = im._extract_disclosure(item)
        self.assertEqual(out[0]["activity_type"], "internal_transfer")
        self.assertFalse(out[0]["signal_eligible"])
        self.assertEqual(out[1]["activity_type"], "share_purchase")
        self.assertTrue(out[1]["signal_eligible"])
        self.assertEqual(out[1]["currency"], "NOK")

    def test_current_euronext_modal_row_is_parsed(self):
        html = """
        <table><tbody><tr>
          <td class="views-field rawmap"><span class="nowrap">27 Aug 2026</span><br><span class="nowrap">10:49 CEST</span></td>
          <td class="views-field views-field-field-company-name">OCEAN SUN</td>
          <td class="views-field views-field-title"><a href="" class="standardRightCompanyPressRelease" data-node-nid="12906847" data-toggle="modal" data-target="#standardRightCompanyPressRelease">Mandatory notification of trade</a></td>
          <td class="views-field">60102020 Renewable Energy Equipment</td>
          <td class="views-field">Mandatory notification of trade primary insiders</td>
        </tr></tbody></table>
        """
        rows = gn.parse_general_euronext_html(html, 20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company"], "OCEAN SUN")
        self.assertEqual(rows[0]["title"], "Mandatory notification of trade")
        self.assertEqual(rows[0]["node_id"], "12906847")
        self.assertEqual(rows[0]["category"], "Insider")
        self.assertTrue(rows[0]["url"].endswith("/en/node/12906847"))
        self.assertTrue(str(rows[0]["published_at"]).startswith("2026-08-27"))

    def test_v2_keeps_official_disclosure_visible_when_detail_is_blocked(self):
        announcement = {
            "company": "SOILTECH ASA",
            "ticker": None,
            "title": "Mandatory notification of trade",
            "category": "Insider",
            "node_id": "123",
            "url": "https://live.euronext.com/en/node/123",
            "published_at": "2026-08-27T08:00:00+00:00",
        }
        source_meta = {"mode":"test","pages_scanned":1,"rows_scanned":1,"filter_live":True}
        im2._CACHE.update({"at": 0.0, "value": None})
        with patch.object(im2, "_announcements", return_value=([announcement], source_meta)), \
             patch.object(im2, "_rows_from_known_provider", return_value=[]), \
             patch.object(im2, "_syndicated_rows", return_value=[]):
            result = im2.market_insider_feed(limit=20, days=14, refresh=True)
        self.assertEqual(result["status"], "live")
        self.assertEqual(result["disclosure_count"], 1)
        self.assertEqual(result["pending_detail_count"], 1)
        self.assertEqual(result["source_meta"], source_meta)
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(result["items"][0]["details_pending"])
        self.assertEqual(result["items"][0]["company"], "SOILTECH ASA")

    def test_insider_topic_url_uses_euronext_taxonomy_and_page(self):
        url = im2._insider_page_url(3)
        self.assertIn("field_company_press_releases_target_id%5B1081%5D=1081", url)
        self.assertTrue(url.endswith("page=3"))


if __name__ == "__main__":
    unittest.main()
