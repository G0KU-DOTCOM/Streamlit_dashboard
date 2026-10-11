import unittest
from unittest.mock import patch,MagicMock
from datetime import datetime,timezone
import pandas as pd
from entsoe_data import flow_intervals,coverage_summary,EntsoeDataError

START=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2025,1,1,1,tzinfo=timezone.utc)
def xml(points,curve='A03',period_start='2025-01-01T00:00Z',period_end='2025-01-01T01:00Z'):
    return f'''<Publication_MarketDocument xmlns="urn:test"><type>A11</type><TimeSeries>
    <out_Domain.mRID>origin</out_Domain.mRID><in_Domain.mRID>destination</in_Domain.mRID>
    <curveType>{curve}</curveType><quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <Period><timeInterval><start>{period_start}</start><end>{period_end}</end></timeInterval>
    <resolution>PT15M</resolution>{''.join(f'<Point><position>{p}</position><quantity>{v}</quantity></Point>' for p,v in points)}
    </Period></TimeSeries></Publication_MarketDocument>'''.encode()
def parse(body,start=START,end=END):return flow_intervals(body,'origin','destination',start,end)

class FlowTests(unittest.TestCase):
    def test_a03_weighted_energy_and_final_block(self):
        frame=parse(xml([(1,100),(2,200)]))
        self.assertEqual(frame.hours.tolist(),[0.25,0.75])
        self.assertEqual(frame.energy_mwh.sum(),175)
        self.assertTrue(coverage_summary(frame,START,END)['complete'])
    def test_a01_gaps_not_filled(self):
        frame=parse(xml([(1,100),(3,200)],'A01'))
        self.assertEqual(frame.energy_mwh.sum(),75)
        self.assertEqual(coverage_summary(frame,START,END)['coverage_percent'],50)
    def test_a03_missing_start_is_not_zero(self):
        frame=parse(xml([(2,200)]))
        self.assertEqual(coverage_summary(frame,START,END)['coverage_percent'],75)
        self.assertFalse(coverage_summary(frame,START,END)['complete'])
    def test_clip_at_requested_boundaries(self):
        frame=parse(xml([(1,100)]),pd.Timestamp('2025-01-01T00:10Z'),pd.Timestamp('2025-01-01T00:50Z'))
        self.assertAlmostEqual(frame.energy_mwh.sum(),100*40/60)
    def test_zero_is_valid(self):
        frame=parse(xml([(1,0)]))
        self.assertTrue(coverage_summary(frame,START,END)['complete'])
        self.assertEqual(frame.energy_mwh.sum(),0)
    def test_invalid_values_positions_and_direction(self):
        for pts in [[(1,100),(1,200)],[(0,1)],[(5,1)],[(1,'NaN')],[(1,-1)]]:
            with self.subTest(points=pts),self.assertRaises(EntsoeDataError):parse(xml(pts))
        with self.assertRaises(EntsoeDataError):parse(xml([(1,10)]).replace(b'origin',b'wrong'))
    def test_overlapping_periods_rejected(self):
        body=xml([(1,100)])
        series=body.split(b'<TimeSeries>')[1].split(b'</TimeSeries>')[0]
        body=body.replace(b'</Publication_MarketDocument>',b'<TimeSeries>'+series+b'</TimeSeries></Publication_MarketDocument>')
        with self.assertRaises(EntsoeDataError):parse(body)
    def test_dst_day_duration_uses_utc(self):
        begin=pd.Timestamp('2025-03-30',tz='Europe/Oslo')
        end=pd.Timestamp('2025-03-31',tz='Europe/Oslo')
        frame=parse(xml([(1,100)],period_start='2025-03-29T23:00Z',period_end='2025-03-30T22:00Z'),begin,end)
        self.assertEqual(frame.energy_mwh.sum(),2300)
        self.assertTrue(coverage_summary(frame,begin,end)['complete'])

if __name__=='__main__':unittest.main()
