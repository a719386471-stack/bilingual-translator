"""Progressive display keeps distant context, cache, and nonblocking quota checks."""
import sys,tempfile,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import helper
import translation_policy as policy
from translation_metrics import timed_translation


class BalancedTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.app=helper.App(self.temp.name)
  self.app.models=lambda *a:[{'slug':'fixture'}]
 def tearDown(self):
  self.app.pool.shutdown();self.app.local_engine.close(cleanup=True);self.app.antigravity.close(cleanup=True);self.temp.cleanup()
 def test_first_result_precedes_completion_without_losing_full_context_or_cache(self):
  paragraphs=['Headline about a bank.','Interest rose.']+['Paragraph '+str(i)+' '+('English source text. '*35) for i in range(10)]
  paragraphs.append('The bank was a lender, not a river bank. Interest meant borrowing costs.')
  payload={'title':'Fixture','paragraphs':paragraphs,'model':'fixture','provider':'chatgpt'}
  entered=threading.Event();release=threading.Event();calls=[]
  def infer(title,paras,previous,model,**kw):
   calls.append(kw['reference'])
   reference={x['id']:x['text'] for x in kw['reference']['article_context']}
   reference.update(zip(kw['reference']['paragraph_ids'],paras))
   self.assertEqual([reference[i] for i in range(len(paragraphs))],paragraphs)
   if len(calls)==2:entered.set();release.wait(2)
   return ['中文 '+p for p in paras]
  self.app.infer=infer
  identifier=self.app.start_job(payload)
  try:
   self.assertTrue(entered.wait(2));state=self.app.snapshot(identifier)
   self.assertEqual(state['status'],'running');self.assertGreater(len(state['results']),0)
   self.assertLess(len(state['results']),len(paragraphs))
  finally:release.set()
  self.wait(identifier)
  self.assertEqual(len(calls),2)
  self.assertEqual(len(self.app.usage.performance()),2)
  self.app.models=lambda *a:(_ for _ in ()).throw(AssertionError('Cached content must not call upstream'))
  self.wait(self.app.start_job(payload));self.assertEqual(len(calls),2)
  self.assertEqual(len(self.app.usage.performance()),2)
 def wait(self,identifier):
  for _ in range(400):
   state=self.app.snapshot(identifier)
   if state['status']!='running':self.assertEqual(state['status'],'done',state);return
   time.sleep(.005)
  self.fail('task did not finish')
 def test_quota_defers_while_translation_runs_and_marks_cached_values(self):
  self.app.config['provider']='antigravity'
  self.app.antigravity.quota=lambda:(_ for _ in ()).throw(AssertionError('Must not query upstream'))
  self.app.jobs['active']={'status':'running','provider':'antigravity'}
  result=self.app.quota();self.assertTrue(result['stale']);self.assertFalse(result['available'])
  self.app.quota_snapshots['antigravity']={'available':True,'windows':[{'remainingPercent':50}],'checkedAt':1}
  result=self.app.quota();self.assertTrue(result['stale']);self.assertEqual(result['checkedAt'],1)
 def test_visible_feed_story_is_first_without_splitting_or_invalidating_cache(self):
  paras=['Story '+str(i) for i in range(16)];groups=['card:'+str(i//2) for i in range(16)]
  old=policy.normalize_options({'newsMode':'feed','groups':groups},paras)
  visible=policy.normalize_options({'newsMode':'feed','groups':groups,'priority':[11]},paras)
  batches=list(policy.plan_batches(range(16),paras,'news',visible))
  self.assertEqual(batches[0][:2],[10,11])
  self.assertEqual(sorted(i for batch in batches for i in batch),list(range(16)))
  self.assertTrue(all(any(i in b and i+1 in b for b in batches) for i in range(0,16,2)))
  self.assertEqual(policy.cache_keys('news','Home',paras,'page','chatgpt','m',old),policy.cache_keys('news','Home',paras,'page','chatgpt','m',visible))
 def test_short_article_is_one_request_and_bad_priority_is_rejected(self):
  paras=['A brief English paragraph.']*6;options=policy.normalize_options({},paras)
  self.assertEqual(list(policy.plan_batches(range(6),paras,'news',options)),[list(range(6))])
  with self.assertRaises(ValueError):policy.normalize_options({'priority':[100]},paras)
 def test_quota_does_not_wait_for_provider_lock(self):
  self.app.config['provider']='antigravity';held=threading.Event();release=threading.Event()
  def hold():
   with self.app.antigravity.lock:held.set();release.wait(2)
  t=threading.Thread(target=hold);t.start();held.wait(1)
  try:
   start=time.monotonic();self.assertTrue(self.app.quota()['stale']);self.assertLess(time.monotonic()-start,.2)
  finally:release.set();t.join()
 def test_timing_distinguishes_queue_setup_and_generation(self):
  result=[]
  with timed_translation(threading.RLock(),result.append) as generation:
   time.sleep(.01);generation();time.sleep(.02)
  self.assertGreaterEqual(result[0]['setup_ms'],8)
  self.assertGreaterEqual(result[0]['generation_ms'],18)
 def test_performance_storage_is_bounded_and_does_not_change_token_totals(self):
  for i in range(505):self.app.usage.record_performance(str(i),'chatgpt','fixture','news',3,500,90,'done',{})
  with self.app.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM translation_performance').fetchone()[0],500)
  self.assertEqual(self.app.usage.summary()['today']['requests'],0)
  self.assertIsNone(self.app.usage.performance()[0]['queue_ms'])

if __name__=='__main__':unittest.main()
