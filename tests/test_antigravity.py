import io,json,queue,sys,tempfile,unittest,threading
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from antigravity_engine import AntigravityEngine
from local_engine import EngineError

class ACPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=AntigravityEngine(self.tmp.name)
 def tearDown(self):
  self.e.close(cleanup=True);self.tmp.cleanup()
 def setup_prompt(self,result,tool=False):
  self.e.models=lambda:[{'slug':'test'}]
  self.e.probe_session={'sessionId':'test-session','models':{'availableModels':[{'modelId':'test'}]}}
  self.e.rpc=lambda *args,**kw:{}
  def send(msg):
   if msg.get('method')=='session/prompt':
    u={'sessionUpdate':'tool_call','toolCallId':'bad'} if tool else {'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'{"translations":["中文"]}'}}
    self.e.events.put({'params':{'sessionId':'test-session','update':u}})
    self.e.pending[msg['id']].put({'result':result})
  self.e.send=send
 def test_official_usage_includes_thoughts_without_double_total(self):
  self.setup_prompt({'stopReason':'end_turn','usage':{'inputTokens':100,'outputTokens':10,'thoughtTokens':40,'totalTokens':150}})
  counts=[];text=self.e.translate('Translate.',{'paragraphs':['English']},'test',counts.append)
  self.assertIn('中文',text);self.assertEqual(counts[0],{'input':100,'output':50,'total':150,'cached':0,'reasoning':40})
 def test_missing_official_usage_is_marked_estimate(self):
  self.setup_prompt({'stopReason':'end_turn'})
  counts=[];self.e.translate('Translate.',{'paragraphs':['English']},'test',counts.append)
  self.assertTrue(counts[0]['estimated']);self.assertGreater(counts[0]['total'],0)
 def test_tools_are_not_accepted_as_translation(self):
  self.setup_prompt({'stopReason':'end_turn'},tool=True)
  with self.assertRaises(EngineError):self.e.translate('Translate.',{},'test')
 def test_permission_requests_cancel_and_file_requests_reject(self):
  sent=[];self.e.send=sent.append
  p=SimpleNamespace(stdout=io.StringIO('\n'.join(json.dumps(m) for m in [
   {'id':1,'method':'session/request_permission'}, {'id':2,'method':'fs/read_text_file'}])))
  self.e._reader(p)
  self.assertEqual(sent[0]['result']['outcome']['outcome'],'cancelled')
  self.assertEqual(sent[1]['error']['code'],-32601)
 def test_cancel_is_forwarded_to_the_official_session(self):
  cancel=threading.Event();sent=[]
  self.e.models=lambda:[];self.e.probe_session={'sessionId':'temporary-session','models':{}}
  def send(msg):
   sent.append(msg)
   if msg['method']=='session/prompt':cancel.set()
  self.e.send=send
  with self.assertRaises(EngineError):self.e.translate('Translate.',{},'test',cancel=cancel)
  self.assertEqual(sent[-1]['method'],'session/cancel')
  self.assertEqual(sent[-1]['params']['sessionId'],'temporary-session')
 def test_only_structured_official_quota_lines_are_parsed(self):
  raw='''- **Gemini Models**
  - **Weekly Limit Remaining:** 93% remaining (resets Nov 04, 2026, 09:11 UTC)
  - **Five Hour Limit Remaining:** 98% remaining (resets Oct 31, 2026, 21:02 UTC)
I guess your plan has 100% left.'''
  rows=self.e.parse_quota(raw)
  self.assertEqual(len(rows),2);self.assertEqual(rows[0]['remainingPercent'],93)
  self.assertEqual(rows[1]['name'],'Gemini · 5 小时额度')
  self.assertEqual(self.e.parse_quota('Your quota is probably 70%.'),[])

if __name__=='__main__':unittest.main()
