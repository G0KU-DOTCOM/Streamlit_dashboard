"""Bounded read-only queries, Norwegian calendar filtering and transfer-page checks."""
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from bson import BSON
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import transfers as t

ROOT = Path(__file__).resolve().parents[1]


def document(stamp=datetime(2025, 1, 1, tzinfo=timezone.utc), **changes):
    return dict(connection='NO2-DK1', time_utc=stamp, import_mwh=10., export_mwh=30.,
                import_coverage_minutes=60., export_coverage_minutes=60.) | changes


def full_frame(connection='NO2-DK1', year=2025):
    start, end, full = t.year_window(connection, year)
    index = pd.date_range(start, end, freq='h', inclusive='left', name='time_utc')
    frame = pd.DataFrame({'import_mwh': 10., 'export_mwh': 30.,
                          'import_coverage_minutes': 60., 'export_coverage_minutes': 60.}, index=index)
    frame.attrs.update(full_year=full, documents=len(frame), bson_bytes=1000, fetched_at='fixture')
    return frame


class TransferDataTests(unittest.TestCase):
    def test_calendar_boundaries_and_partial_years(self):
        start, end, full = t.year_window('NO2-DK1', 2025)
        self.assertEqual(start, datetime(2024, 12, 31, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2025, 12, 31, 23, tzinfo=timezone.utc))
        self.assertTrue(full)
        self.assertFalse(t.year_window('NO2-DK1', 2024)[2])
        self.assertFalse(t.year_window('NO2-DK1', 2026)[2])
        for connection, year in [('invalid', 2025), ('NO2-DK1', 2023)]:
            with self.assertRaises(t.FlowDataError): t.year_window(connection, year)

    def test_pilot_never_becomes_annual_total_and_missing_is_not_zero(self):
        frame = t.prepare_flows([document()], 'NO2-DK1', 2025)
        self.assertEqual(len(frame), 8760)
        self.assertEqual(t.complete_hours(frame).sum(), 1)
        self.assertIsNone(t.period_totals(frame))
        self.assertTrue(pd.isna(frame.iloc[0].import_mwh))
        zero = t.prepare_flows([document(import_mwh=0.)], 'NO2-DK1', 2025)
        self.assertEqual(zero.loc['2025-01-01T00:00:00Z', 'import_mwh'], 0.)
        partial = t.prepare_flows([document(import_coverage_minutes=30)], 'NO2-DK1', 2025)
        self.assertTrue(pd.isna(partial.loc['2025-01-01T00:00:00Z', 'import_mwh']))

    def test_invalid_and_duplicate_documents_stop(self):
        for docs in [[document(), document()], [document(import_mwh=-1)],
                     [document(export_mwh=float('nan'))], [document(export_coverage_minutes=61)],
                     [document(connection='NO1-SE3')], [document(datetime(2023, 1, 1, tzinfo=timezone.utc))],
                     [document(datetime(2025, 1, 1))]]:
            with self.subTest(docs=len(docs)), self.assertRaises(t.FlowDataError):
                t.prepare_flows(docs, 'NO2-DK1', 2025)

    def test_query_bounds_projection_and_cursor_closure(self):
        collection = MagicMock()
        cursor = collection.find.return_value
        cursor.hint.return_value = cursor
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.batch_size.return_value = cursor
        cursor.__iter__.return_value = iter([document()])
        result = t.read_year(collection, 'NO2-DK1', 2025)
        self.assertEqual(result.attrs['documents'], 1)
        query, projection = collection.find.call_args.args
        self.assertEqual(query['connection'], 'NO2-DK1')
        self.assertEqual(set(query['time_utc']), {'$gte', '$lt'})
        self.assertEqual(projection['_id'], 0)
        self.assertEqual(collection.find.call_args.kwargs['max_time_ms'], 10000)
        cursor.hint.assert_called_once_with([('connection', 1), ('time_utc', 1)])
        cursor.limit.assert_called_once_with(8785)
        cursor.close.assert_called_once()
        collection.insert_one.assert_not_called()
        collection.create_index.assert_not_called()
        with patch.object(t, 'MAX_BSON_BYTES', 1):
            cursor.__iter__.return_value = iter([document()])
            with self.assertRaises(t.FlowDataError): t.read_year(collection, 'NO2-DK1', 2025)
        self.assertEqual(cursor.close.call_count, 2)

    def test_exact_byte_and_row_limits(self):
        doc = document()
        with patch.object(t, 'MAX_BSON_BYTES', len(BSON.encode(doc))):
            self.assertEqual(t.prepare_flows([doc], 'NO2-DK1', 2025).attrs['documents'], 1)
        with patch.object(t, 'MAX_DOCUMENTS', 1), self.assertRaises(t.FlowDataError):
            t.prepare_flows([doc, document(datetime(2025, 1, 1, 1, tzinfo=timezone.utc))], 'NO2-DK1', 2025)

    def test_month_gaps_dst_and_pie_are_independent(self):
        frame = full_frame()
        january_march = t.month_lines(frame, [1, 3])
        months = january_march.index.tz_convert(t.OSLO).month
        self.assertTrue(january_march.loc[months == 2].isna().all().all())
        self.assertEqual(january_march.loc[months == 3].notna().all(axis=1).sum(), 743)
        october = t.month_lines(frame, [10])
        self.assertEqual(len(october), 745)
        self.assertEqual(len(october.index.unique()), 745)
        self.assertTrue(t.month_lines(frame, []).empty)
        self.assertEqual(t.period_totals(frame).tolist(), [87600., 262800.])
        pie = t.pie_figure(t.period_totals(frame))
        labels = [text.get_text() for text in pie.axes[0].texts]
        self.assertIn('25.0%', labels)
        self.assertIn('75.0%', labels)
        graph = t.line_figure(frame, [1, 3])
        self.assertTrue(np.isnan(graph.axes[0].lines[0].get_ydata()[months == 2]).all())

    def test_read_failure_hides_details_and_is_cached(self):
        t.load_flows.clear()
        self.addCleanup(t.load_flows.clear)
        client = MagicMock()
        with patch.object(t, 'mongo_client', return_value=client), patch.object(
                t, 'read_year', side_effect=t.FlowDataError('Safe failure')) as read:
            for _ in range(2): self.assertEqual(t.load_flows('NO2-DK1', 2025)['error'], 'Safe failure')
            self.assertEqual(read.call_count, 1)
        collection = MagicMock()
        collection.find.side_effect = RuntimeError('secret URI must never be printed')
        with self.assertRaises(t.FlowDataError) as caught: t.read_year(collection, 'NO2-DK1', 2025)
        self.assertNotIn('secret URI', str(caught.exception))

    def test_success_cache_is_bounded_to_year_not_month(self):
        t.load_flows.clear()
        self.addCleanup(t.load_flows.clear)
        with patch.object(t, 'mongo_client', return_value=MagicMock()), patch.object(
                t, 'read_year', return_value=full_frame()) as read:
            first = t.load_flows('NO2-DK1', 2025)['frame']
            first.iloc[0, 0] = -5
            second = t.load_flows('NO2-DK1', 2025)['frame']
            self.assertEqual(second.iloc[0, 0], 10.)
            t.month_lines(second, [1, 3])
            self.assertEqual(read.call_count, 1)


class TransferPageTests(unittest.TestCase):
    def setUp(self):
        # None of these UI tests may contact Atlas or NVE.
        self.enterContext(patch.object(t, 'mongo_client', side_effect=AssertionError('No live database')))
        self.loader = self.enterContext(patch.object(t, 'load_flows', side_effect=lambda connection, year: {
            'frame': full_frame(connection, year), 'error': None}))

    def app(self):
        return AppTest.from_file(str(ROOT/'main.py')).run().switch_page('pages/4_Cross_Border_Transfers.py').run()

    def test_complete_year_and_multiple_months(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.columns), 2)
        pills = app.get('button_group')[0]
        pills.set_value([1, 3]).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.warning)
        app.get('button_group')[0].set_value([]).run()
        self.assertTrue(any('Select one or more' in x.value for x in app.info))
        app.selectbox[0].set_value(2024).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('partial year' in x.value for x in app.subheader))

    def test_incomplete_and_unavailable_data(self):
        self.loader.side_effect = lambda connection, year: {'frame': t.prepare_flows([], connection, year), 'error': None}
        app = self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any('pie is withheld' in x.value for x in app.warning))
        self.loader.side_effect = None
        self.loader.return_value = {'frame': None, 'error': 'Safe connection error'}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.error[0].value, 'Safe connection error')


if __name__ == '__main__': unittest.main()
