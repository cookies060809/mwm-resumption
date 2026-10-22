"""Budget and balance controls use fake predictions; no provider calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_external_resumable as runner


class FakeMethod:
    def availability(self):
        return {'available': True}


class ResumableControlsTest(unittest.TestCase):
    def invoke(self, output, fake_predict, **kwargs):
        with patch.object(runner, 'make_external_baselines', return_value={'B9': FakeMethod()}), \
             patch.object(runner, 'predict_rows', side_effect=fake_predict):
            runner.run(runner.ROOT/'configs/deepseek_mentis_p0.json', output, ['B9'], 1, **kwargs)

    def test_balance_error_persists_one_row_and_stops_before_next_sample(self):
        calls=[]
        def predict(method, records, seed):
            calls.append(records[0]['sample_id'])
            return [{'method_id':'B9','sample_id':calls[-1],'status':'error',
                     'failure_metadata':{'raw_output':'Error code: 402 Insufficient Balance'}}]
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            with self.assertRaisesRegex(RuntimeError, 'API402_CIRCUIT_OPEN'):
                self.invoke(output,predict)
            self.assertEqual(len(calls),1)
            self.assertEqual(len((output/'predictions.jsonl').read_text().splitlines()),1)
            self.assertFalse((output/'summary.json').exists())

    def test_token_threshold_prevents_next_sample_and_reports_partial_run(self):
        calls=[]
        def predict(method, records, seed):
            calls.append(records[0]['sample_id'])
            return [{'method_id':'B9','sample_id':calls[-1],'status':'ok','usage':{'total_tokens':11}}]
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            self.invoke(output,predict,max_new_tokens=10)
            self.assertEqual(len(calls),1)
            progress=json.loads((output/'progress.json').read_text())
            self.assertEqual(progress['new_known_tokens'],11)
            self.assertFalse((output/'summary.json').exists())
