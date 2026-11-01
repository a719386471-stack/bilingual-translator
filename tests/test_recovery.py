import sys,tempfile,time,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import helper
from unittest.mock import patch

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=helper.App(self.tmp.name)
  self.app.models=lambda *args:[{'slug':'test'}]
  self.app.retry_wait=lambda job,seconds:job['cancel'].is_set()
  self.paras=[('English paragraph number %d, with context and complete sentences.'%i).ljust(1300,'x') for i in range(14)]
  self.payload={'title':'Recovery test','paragraphs':self.paras,'model':'test','pageKey':'a'*64,'requestId':'1'*32}
 def tearDown(self):
  self.app.pool.shutdown();self.app.local_engine.close(cleanup=True);self.app.antigravity.close(cleanup=True);self.tmp.cleanup()
 def wait(self,id):
  for _ in range(300):
   s=self.app.snapshot(id)
   if s['status']!='running':return s
   time.sleep(.01)
  self.fail('task did not finish')
 def test_only_failed_batch_retried_and_each_billed_attempt_counted(self):
  calls=[];failed=False
  def infer(title,paras,previous,model,**kw):
   nonlocal failed
   calls.append(paras)
   kw['on_usage']({'input':100,'output':20,'total':120,'cached':0,'reasoning':0})
   if paras[0]==self.paras[6] and not failed:
    failed=True;raise helper.AppError('网络断开','connection',True)
   return ['中文 '+p for p in paras]
  self.app.infer=infer
  state=self.wait(self.app.start_job(self.payload))
  self.assertEqual(state['status'],'done');self.assertEqual(len(state['results']),14)
  self.assertEqual([p[0] for p in calls],[self.paras[0],self.paras[6],self.paras[6],self.paras[12]])
  self.assertEqual(self.app.usage.summary()['today']['total'],480)
 def test_quota_stops_without_automatic_retry_and_manual_resume_keeps_results(self):
  calls=[];quota=True
  def infer(title,paras,previous,model,**kw):
   calls.append(paras[0])
   if quota and paras[0]==self.paras[6]:raise helper.AppError('额度不足','quota')
   return ['中文']*len(paras)
  self.app.infer=infer
  id=self.app.start_job(self.payload);s=self.wait(id)
  self.assertEqual(s['status'],'error');self.assertFalse(s['retryable']);self.assertEqual(s['errorCode'],'quota')
  self.assertEqual(len(s['results']),6);self.assertEqual(len(calls),2)
  quota=False
  self.assertEqual(self.app.start_job({**self.payload,'resume':True}),id)
  self.assertEqual(len(self.wait(id)['results']),14)
  self.assertEqual(calls.count(self.paras[0]),1)
 def test_timed_out_post_is_idempotent_and_conflicting_reuse_is_rejected(self):
  calls=[];gate=threading.Event()
  def infer(title,paras,*args,**kw):calls.append(paras);gate.wait(1);return ['中文']*len(paras)
  self.app.infer=infer
  id=self.app.start_job(self.payload)
  for _ in range(5):self.assertEqual(self.app.start_job(self.payload),id)
  with self.assertRaises(helper.AppError):self.app.start_job({**self.payload,'title':'Different data'})
  gate.set();self.assertEqual(self.wait(id)['status'],'done')
  self.assertEqual(len(calls),3)
  self.app.start_job(self.payload);time.sleep(.03);self.assertEqual(len(calls),3)
 def test_caption_windows_share_cache_and_send_one_model_request_for_24_cues(self):
  calls=[]
  def infer(title,paras,*args,**kw):calls.append(paras);return ['中文']*len(paras)
  self.app.infer=infer
  cues=['English caption number %d for window reuse.'%i for i in range(40)]
  payload={**self.payload,'kind':'captions','paragraphs':cues[:24],'cueIds':list(range(24))}
  self.assertEqual(self.wait(self.app.start_job(payload))['status'],'done');self.assertEqual(len(calls),1)
  self.wait(self.app.start_job({**payload,'requestId':'2'*32,'paragraphs':cues[12:36],'cueIds':list(range(12,36))}))
  self.assertEqual(len(calls),2);self.assertEqual(calls[1],cues[24:36])
  # Reopening after a helper restart uses the same SQLite cache without asking the model catalog.
  self.app.jobs.clear();self.app.models=lambda *args:(_ for _ in ()).throw(AssertionError('cache must work offline'))
  self.assertEqual(self.wait(self.app.start_job(payload))['status'],'done');self.assertEqual(len(calls),2)
 def test_format_failure_is_bounded_and_cancel_interrupts_backoff(self):
  calls=[]
  def bad(*args,**kw):calls.append(1);raise helper.AppError('格式无效','format',True)
  self.app.infer=bad;s=self.wait(self.app.start_job(self.payload))
  self.assertEqual(s['status'],'error');self.assertEqual(len(calls),2)
  self.app.retry_wait=lambda job,seconds:(job['cancel'].set() or True)
  self.app.infer=lambda *args,**kw:(_ for _ in ()).throw(helper.AppError('断开','connection',True))
  s=self.wait(self.app.start_job({**self.payload,'requestId':'3'*32}))
  self.assertEqual(s['status'],'cancelled')
 def test_stream_socket_loss_is_classified_for_retry(self):
  class BrokenStream:
   def __iter__(self):raise OSError('test connection reset')
  self.app.access_token=lambda:'fixture-only'
  with patch('helper.remote') as remote:
   remote.return_value.__enter__.return_value=BrokenStream()
   with self.assertRaises(helper.AppError) as caught:self.app.infer('News',['English'],[],'fixture')
  self.assertTrue(caught.exception.retryable);self.assertEqual(caught.exception.code,'connection')

if __name__=='__main__':unittest.main()
