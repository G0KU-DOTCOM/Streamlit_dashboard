import json
from pathlib import Path
import unittest
import pandas as pd
from pipeline.entsoe_bulk import segments

class BulkPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads(Path('entsoe_plan.json').read_text())
        self.jobs=list(segments(self.plan))
    def test_exactly_54_unique_jobs(self):
        self.assertEqual(len(self.jobs),54)
        self.assertEqual(len({j['id'] for j in self.jobs}),54)
        self.assertEqual(len({j['cache_name'] for j in self.jobs}),54)
    def test_each_direction_covers_exact_window_without_overlap(self):
        for c in self.plan['connections']:
            for direction in self.plan['directions']:
                jobs=[j for j in self.jobs if j['connection']==c['connection'] and j['direction']==direction]
                self.assertEqual(pd.Timestamp(jobs[0]['start']),pd.Timestamp(self.plan['period']['start_inclusive']))
                self.assertEqual(pd.Timestamp(jobs[-1]['end']),pd.Timestamp(self.plan['period']['end_exclusive']))
                self.assertTrue(all(a['end']==b['start'] for a,b in zip(jobs,jobs[1:])))
                hours=sum((pd.Timestamp(j['end'])-pd.Timestamp(j['start'])).total_seconds()/3600 for j in jobs)
                self.assertEqual(hours,17520)
    def test_directions_are_relative_to_norway(self):
        mapping={c['connection']:c for c in self.plan['connections']}
        for j in self.jobs:
            c=mapping[j['connection']]
            expected=(c['foreign_eic'],c['norwegian_eic']) if j['direction']=='import' else (c['norwegian_eic'],c['foreign_eic'])
            self.assertEqual((j['origin'],j['destination']),expected)
    def test_cached_full_year_files_are_reused(self):
        files=[j['cache_name'] for j in self.jobs if j['connection']=='NO2-DK1' and pd.Timestamp(j['start']).year==2025]
        self.assertEqual(set(files),{'NO2_DK1_2025_import.xml','NO2_DK1_2025_export.xml'})
    def test_budget_counts_probes_plus_remaining_downloads(self):
        self.assertLessEqual(16+54-2,self.plan['planned_limits']['max_total_request_attempts'])

if __name__=='__main__':unittest.main()
