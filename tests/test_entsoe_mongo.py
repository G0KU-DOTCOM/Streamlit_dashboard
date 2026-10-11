import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock
from entsoe_mongo import admit,number,missing_documents,ensure_index,split_batches,UploadStopped,RESERVE_BYTES

class MongoGuardTests(unittest.TestCase):
    def setUp(self):
        self.limits=json.loads(Path('entsoe_plan.json').read_text())['planned_limits']
        self.stats={'project_bytes':0,'cluster_bytes':36950,'collection':{'documents':0,'data_bytes':0,'index_bytes':0}}
    def test_full_payload_and_margin_fit(self):
        result=admit(self.stats,self.limits,remaining_bytes=29135760)
        self.assertEqual(result['projected_project_bytes'],2*29135760+RESERVE_BYTES)
        self.assertLess(result['projected_project_bytes'],64*1024**2)
    def test_project_limit_stops_before_next_batch(self):
        self.stats['project_bytes']=64*1024**2-RESERVE_BYTES
        with self.assertRaises(UploadStopped):admit(self.stats,self.limits,remaining_bytes=1)
    def test_other_databases_count_against_cluster_limit(self):
        self.stats['cluster_bytes']=250*1024**2
        with self.assertRaises(UploadStopped):admit(self.stats,self.limits,remaining_bytes=29135760)
    def test_indexes_count_and_batch_reservation(self):
        self.stats['project_bytes']=63*1024**2
        with self.assertRaises(UploadStopped):admit(self.stats,self.limits,remaining_bytes=0,batch_bytes=100)
    def test_document_ceiling(self):
        self.stats['collection']['documents']=160000
        with self.assertRaises(UploadStopped):admit(self.stats,self.limits,remaining_bytes=0,new_documents=1)
    def test_missing_statistics_fail_closed(self):
        for value in [None,-1,float('nan'),'123']:
            with self.assertRaises(UploadStopped):number({'size':value},'size')
        with self.assertRaises(UploadStopped):number({},'size')
    def test_existing_identical_document_skipped(self):
        coll=MagicMock();coll.find.return_value.limit.return_value=[{'_id':'a','value':1}]
        self.assertEqual(missing_documents(coll,[{'_id':'a','value':1},{'_id':'b','value':2}]),[{'_id':'b','value':2}])
    def test_existing_different_document_blocks(self):
        coll=MagicMock();coll.find.return_value.limit.return_value=[{'_id':'a','value':9}]
        with self.assertRaises(UploadStopped):missing_documents(coll,[{'_id':'a','value':1}])
        coll.bulk_write.assert_not_called()
    def test_unexpected_index_blocks(self):
        coll=MagicMock();coll.list_indexes.return_value=[{'name':'_id_','key':{'_id':1}}, {'name':'extra','key':{'value':1}}]
        with self.assertRaises(UploadStopped):ensure_index(coll)
        coll.create_index.assert_not_called()
    def test_expected_index_reused(self):
        coll=MagicMock();coll.list_indexes.return_value=[{'name':'_id_','key':{'_id':1}}, {'name':'connection_time_utc','key':{'connection':1,'time_utc':1},'unique':True}]
        ensure_index(coll);coll.create_index.assert_not_called()
    def test_batches_do_not_exceed_forty(self):
        batches=list(split_batches(range(85)))
        self.assertEqual([len(b) for b in batches],[40,40,5])
        self.assertEqual(sum(batches,[]),list(range(85)))

if __name__=='__main__':unittest.main()
