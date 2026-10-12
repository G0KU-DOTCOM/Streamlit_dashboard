from datetime import datetime,timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from bson import decode_all

from pipeline.entsoe_hourly import hourly_flows,write_bson,document_from_row
from pipeline.entsoe_storage import StorageStopped


def document_row(epoch=1735689600):
    return {'connection':'NO2-DK1','hour_epoch':epoch,'import_mwh':12.5,'export_mwh':0.0,
            'import_coverage_minutes':60.0,'export_coverage_minutes':60.0}


class BsonTests(unittest.TestCase):
    def test_stable_utc_id_and_explicit_zero(self):
        doc=document_from_row(document_row())
        self.assertEqual(doc['_id'],'NO2-DK1|20250101T0000Z')
        self.assertEqual(doc['time_utc'].tzinfo,timezone.utc)
        self.assertEqual(doc['export_mwh'],0.0)
    def test_actual_encoded_size_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.bson'
            result=write_bson([document_row(),document_row(1735693200)],path,max_documents=2,max_bytes=1000)
            self.assertEqual(result['bson_bytes'],path.stat().st_size)
            docs=decode_all(path.read_bytes())
            self.assertEqual(len(docs),2)
            self.assertEqual(docs[0]['import_mwh'],12.5)
            self.assertNotEqual(docs[0]['_id'],docs[1]['_id'])
    def test_limits_preserve_previous_file(self):
        for max_documents,max_bytes in [(1,1000),(10,1)]:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'data.bson';path.write_bytes(b'previous')
                with self.assertRaises(StorageStopped):
                    write_bson([document_row(),document_row(1735693200)],path,max_documents=max_documents,max_bytes=max_bytes)
                self.assertEqual(path.read_bytes(),b'previous')
                self.assertFalse(path.with_suffix('.tmp').exists())
    def test_missing_energy_stays_null(self):
        row=document_row();row.update(import_mwh=None,import_coverage_minutes=0.0)
        self.assertIsNone(document_from_row(row)['import_mwh'])
    def test_invalid_values_rejected(self):
        for name,value in [('import_mwh',-1),('export_mwh',float('nan')),('import_coverage_minutes',61)]:
            row=document_row();row[name]=value
            with self.assertRaises(StorageStopped):document_from_row(row)


@unittest.skipUnless(os.environ.get('RUN_SPARK_TESTS')=='1','Set RUN_SPARK_TESTS=1 for local Spark math tests')
class HourlySparkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyspark.sql import SparkSession
        os.environ['JAVA_HOME']=subprocess.check_output(['/usr/libexec/java_home','-v','17'],text=True).strip()
        os.environ['SPARK_LOCAL_IP']='127.0.0.1'
        os.environ['PYSPARK_PYTHON']=sys.executable
        os.environ['PYSPARK_DRIVER_PYTHON']=sys.executable
        cls.spark=(SparkSession.builder.master('local[1]').appName('HourlyMathChecks')
            .config('spark.sql.session.timeZone','UTC').config('spark.ui.enabled','false')
            .config('spark.sql.shuffle.partitions','1').getOrCreate())
        cls.spark.sparkContext.setLogLevel('ERROR')
    @classmethod
    def tearDownClass(cls):cls.spark.stop()
    def compute(self,intervals,start='2025-01-01T00:00:00+00:00',end='2025-01-01T02:00:00+00:00'):
        begin=datetime.fromisoformat(start);finish=datetime.fromisoformat(end)
        from datetime import timedelta
        raw=self.spark.createDataFrame([('NO2-DK1',d,begin+timedelta(minutes=a),begin+timedelta(minutes=b),float(p))
            for d,a,b,p in intervals],'connection string, direction string, start_utc timestamp, end_utc timestamp, power_mw double')
        return hourly_flows(raw,begin,finish,['NO2-DK1']).orderBy('hour_utc').collect()
    def test_weighted_energy_not_mean_of_points(self):
        rows=self.compute([('import',0,15,100),('import',15,60,200)])
        self.assertEqual(rows[0].import_mwh,175.0)
        self.assertEqual(rows[0].import_coverage_minutes,60)
    def test_interval_split_across_hours_preserves_energy(self):
        rows=self.compute([('export',30,90,120)])
        self.assertEqual([r.export_mwh for r in rows],[60.0,60.0])
        self.assertEqual([r.export_coverage_minutes for r in rows],[30.0,30.0])
    def test_end_exclusive_and_zero_distinct_from_missing(self):
        rows=self.compute([('import',0,60,0)])
        self.assertEqual(rows[0].import_mwh,0)
        self.assertIsNone(rows[1].import_mwh)
        self.assertEqual(rows[1].import_coverage_minutes,0)
        self.assertIsNone(rows[0].export_mwh)
    def test_nested_overlap_is_rejected(self):
        with self.assertRaises(StorageStopped):
            self.compute([('import',0,120,100),('import',15,30,100)])
    def test_dst_repeated_local_hour_keeps_two_utc_hours(self):
        rows=self.compute([('import',0,120,100)],start='2025-10-26T00:00:00+00:00',end='2025-10-26T02:00:00+00:00')
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(r.import_mwh for r in rows),200)
    def test_invalid_power_rejected(self):
        with self.assertRaises(StorageStopped):self.compute([('import',0,60,-1)])


if __name__=='__main__':unittest.main()
