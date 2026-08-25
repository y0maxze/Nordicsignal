import unittest

from stock_intelligence_runtime import classify_news_title
from dividend_runtime import _extract_events


class StockIntelligenceRuntimeTests(unittest.TestCase):
    def test_news_classification(self):
        self.assertEqual(classify_news_title('Q2 2026 results and interim report'), 'Rapport')
        self.assertEqual(classify_news_title('Mandatory notification of trade by primary insider'), 'Insider')
        self.assertEqual(classify_news_title('Board proposes NOK 2.50 dividend'), 'Utbytte')
        self.assertEqual(classify_news_title('Company wins major contract'), 'Selskap')
        self.assertEqual(classify_news_title('General market update'), 'Nyhet')

    def test_dividend_event_extraction_sorts_and_ignores_bad_rows(self):
        data={'chart':{'result':[{'events':{'dividends':{
            '1672531200':{'date':1672531200,'amount':2.5},
            '1675209600':{'date':1675209600,'amount':1.25},
            'bad':{'date':'x','amount':3},
            'zero':{'date':1677628800,'amount':0},
        }}}]}}
        out=_extract_events(data)
        self.assertEqual(len(out),2)
        self.assertEqual(out[0]['amount'],2.5)
        self.assertEqual(out[1]['amount'],1.25)
        self.assertEqual(out[0]['date'],'2023-01-01')

    def test_dividend_event_extraction_handles_empty_data(self):
        self.assertEqual(_extract_events({}),[])
        self.assertEqual(_extract_events({'chart':{'result':None}}),[])


if __name__=='__main__':
    unittest.main()
