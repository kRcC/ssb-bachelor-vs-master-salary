"""Kjør: python -m unittest discover -s tests -v."""
import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import main

RECORDS = [
    (2025, '541', 'IT', '3', Decimal('50000'), Decimal('48000'), 1000),
    (2025, '541', 'IT', '4', Decimal('60000'), Decimal('58000'), 800),
    (2025, '411', 'Økonomi', '3', Decimal('50000'), Decimal('48000'), 900),
    (2025, '411', 'Økonomi', '4', None, None, 700),
    (2025, '551', 'Elektro', '3', Decimal('60000'), Decimal('59000'), 90),
    (2025, '551', 'Elektro', '4', Decimal('55000'), Decimal('54000'), 100),
    (2024, '541', 'IT', '4', Decimal('90000'), Decimal('88000'), 800),
]


class DataCheck(unittest.TestCase):
    def test_source_dimensions_and_missing_values(self):
        codes = {'Tid': ['2025'], 'MaaleMetode': ['02', '01', '10'], 'UtdNivaa': ['3', '4'],
                 'Fagfelt': ['541'], 'AntAarEtterUtd': ['00-02'], 'AvtaltArbTid': ['5'],
                 'ContentsCode': ['Manedslonn']}
        dataset = {'id': list(codes), 'size': [len(c) for c in codes.values()],
                   'dimension': {k: {'category': {'index': {v: i for i, v in enumerate(c)}}}
                                 for k, c in codes.items()}, 'value': [50000, None, 48000, None, 1000, 800]}
        dataset['dimension']['Fagfelt']['category']['label'] = {'541': 'IT'}
        self.assertEqual(main.rows_from_dataset(dataset), [
            (2025, '541', 'IT', '3', 50000, 48000, 1000), (2025, '541', 'IT', '4', None, None, 800)])
        for index, invalid in [(0, 0), (0, -1), (0, float('nan')), (0, '50000'), (0, True), (4, 1.5)]:
            broken = copy.deepcopy(dataset)
            broken['value'][index] = invalid
            with self.assertRaises(ValueError):
                main.rows_from_dataset(broken)
        broken = copy.deepcopy(dataset)
        broken['value'].pop()
        with self.assertRaises(ValueError):
            main.rows_from_dataset(broken)

    def test_comparison_matches_year_group_measure_and_threshold(self):
        rows = main.compare_fields(RECORDS, 2025, 'median', 100)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Bachelor (kr/mnd)'], 48000)
        self.assertEqual(rows[0]['Master (kr/mnd)'], 58000)
        self.assertEqual(rows[0]['Forskjell (kr/mnd)'], 10000)
        self.assertEqual(len(main.compare_fields(RECORDS, 2025, 'mean')), 2)
        self.assertEqual(main.compare_fields(RECORDS, 2024, 'mean'), [])

    def test_scenario_break_even_and_invalid_inputs(self):
        self.assertEqual(main.scenario(50000, 60000, 2, 0, 0), (1200000, 10))
        cost, years = main.scenario(50000, 60000, 2, 10000, 120000)
        self.assertEqual((cost, years), (1080000, 9))
        for master in [50000, 40000]:
            self.assertIsNone(main.scenario(50000, master, 2, 0, 0)[1])
        elapsed = 2 + years
        self.assertEqual(elapsed * 12 * 50000, 2 * 12 * 10000 + (elapsed - 2) * 12 * 60000 - 120000)
        for values in [(0, 60000, 2, 0, 0), (50000, 60000, 0, 0, 0),
                       (50000, 60000, 2, 60000, 0), (50000, 60000, 2, 0, -1),
                       (float('nan'), 60000, 2, 0, 0)]:
            with self.assertRaises(ValueError):
                main.scenario(*values)

    def test_import_transaction_and_source_failure(self):
        with patch.object(main, 'fetch_ssb_rows', return_value=RECORDS[:2]), patch.object(main, 'connect') as connect:
            connection = connect.return_value.__enter__.return_value
            cursor = connection.cursor.return_value.__enter__.return_value
            main.load()
            self.assertEqual(cursor.executemany.call_args.args[1], RECORDS[:2])
            connection.commit.assert_called_once_with()
            connection.rollback.assert_not_called()
            connection.reset_mock()
            cursor.executemany.side_effect = RuntimeError('write failure')
            with self.assertRaises(RuntimeError):
                main.load()
            connection.rollback.assert_called_once_with()
            connection.commit.assert_not_called()
        with patch.object(main, 'fetch_ssb_rows', side_effect=ValueError('invalid source')), patch.object(main, 'connect') as connect:
            with self.assertRaises(ValueError):
                main.load()
            connect.assert_not_called()

    def test_empty_database(self):
        with patch.object(main, 'connect') as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = []
            with self.assertRaises(ValueError):
                main.fetch_records('test-only')

    def test_streamlit_controls_and_database_failure(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 0)
        with patch('src.main.fetch_records', return_value=RECORDS):
            app.text_input[0].set_value('test-only').run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[0].value, '48 000 kr')
            self.assertEqual(app.metric[3].value, 'kr 11 520 000')
            self.assertEqual(app.metric[4].value, 'kr 12 528 000')
            self.assertEqual(app.metric[5].value, 'kr +1 008 000')
            self.assertIn('9.6', app.success[0].value)
            app.number_input[1].set_value(3).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn('14.4', app.success[0].value)
            app.selectbox[1].set_value('mean').run()
            self.assertEqual(app.metric[0].value, '50 000 kr')
            app.number_input[0].set_value(0).run()
            app.selectbox[2].set_value('551').run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.success), 0)
            self.assertGreater(len(app.warning), 0)
        with patch('src.main.fetch_records', side_effect=RuntimeError('private details')):
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 1)
            self.assertNotIn('private details', app.error[0].value)
            self.assertEqual(len(app.metric), 0)

    def test_streamlit_requires_password_even_with_saved_secret(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30)
        app.secrets['ssb_mysql_password'] = 'unused-secret'
        with patch('src.main.fetch_records', return_value=RECORDS) as fetch:
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_input), 1)
            self.assertEqual(len(app.metric), 0)
            fetch.assert_not_called()
            app.text_input[0].set_value('test-only').run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.metric), 6)
            fetch.assert_called_once_with('test-only')
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_input), 1)

    def test_export_and_break_even_marker_follow_scenario(self):
        import csv
        from io import StringIO
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
        with patch('src.main.fetch_records', return_value=RECORDS), \
                patch('streamlit.download_button', return_value=False) as download, \
                patch('streamlit.altair_chart') as plot:
            app.text_input[0].set_value('test-only').run()
            self.assertEqual(len(app.exception), 0)
            exported = list(csv.DictReader(StringIO(download.call_args.kwargs['data'].decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(len(exported), 21)
            self.assertEqual(exported[-1]['Bachelor (kr)'], '11520000,00')
            self.assertEqual(exported[-1]['Master (kr)'], '12528000,00')
            self.assertEqual(exported[-1]['Forskjell (kr)'], '1008000,00')
            self.assertEqual(exported[0]['År til lik inntekt fra valget'], '11,60')
            self.assertNotIn('test-only', download.call_args.kwargs['data'].decode('utf-8-sig'))
            spec = plot.call_args.args[0].to_dict()
            self.assertEqual(len(spec['layer']), 4)
            marker_data = spec['layer'][1]['data']['values'][0]
            self.assertAlmostEqual(marker_data['År fra valget'], 11.6)
            app.slider[0].set_value(5).run()
            self.assertEqual(len(app.exception), 0)
            self.assertNotIn('layer', plot.call_args.args[0].to_dict())
            self.assertTrue(any('utenfor grafen' in info.value for info in app.info))
            app.number_input[0].set_value(0).run()
            app.selectbox[2].set_value('551').run()
            self.assertEqual(len(app.exception), 0)
            exported = list(csv.DictReader(StringIO(download.call_args.kwargs['data'].decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(exported[0]['År til lik inntekt fra valget'], '')
            self.assertNotIn('layer', plot.call_args.args[0].to_dict())


if __name__ == '__main__':
    unittest.main()
