import tempfile
import unittest
from pathlib import Path
from engagement import summarize_metrics

class EngagementTests(unittest.TestCase):
    def test_aggregates_real_metrics_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'metrics.csv'
            path.write_text('post_id,topic,impressions,comments,shares\na,SQL,100,2,1\nb,SQL,300,1,0\n')
            result=summarize_metrics(path)
            self.assertEqual(result['topics'][0]['interaction_rate'],.01)
            self.assertEqual(result['topics'][0]['posts'],2)
            path.write_text('post_id,topic,impressions,comments,shares\na,SQL,100,2,1\na,SQL,300,1,0\n')
            with self.assertRaises(ValueError):summarize_metrics(path)
    def test_empty_file_has_no_invented_performance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'metrics.csv';path.write_text('post_id,topic,impressions,comments,shares\n')
            self.assertEqual(summarize_metrics(path)['topics'],[])
