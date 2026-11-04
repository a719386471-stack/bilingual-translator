"""Caption identity and partial delivery regressions, without model calls."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import translation_policy as policy
from helper import parse_translation,AppError

class CaptionStreamingTests(unittest.TestCase):
 def test_live_job_publishes_completed_cue_before_caching_complete_batch(self):
  import tempfile,threading,time
  from helper import App
  with tempfile.TemporaryDirectory() as directory:
   app=App(directory);app.config['engine']='local';app.models=lambda *a:[{'slug':'fixture'}]
   ready=threading.Event();release=threading.Event()
   def translate(prompt,payload,model,**kw):
    self.assertEqual([s['id'] for s in payload['segments']],['7','8'])
    kw['on_text']('{"translations":{"7":"看见。",');ready.set();release.wait(2)
    return '{"translations":{"8":"我能问一下吗？","7":"看见。"}}'
   app.local_engine.translate=translate
   try:
    job=app.start_job({'kind':'captions','model':'fixture','paragraphs':['to see.','Can I ask?'],'cueIds':[7,8]})
    self.assertTrue(ready.wait(2));state=app.snapshot(job)
    self.assertEqual(state['status'],'running');self.assertEqual(state['results'],{'0':'看见。'})
    with app.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM translations').fetchone()[0],0)
    release.set()
    for _ in range(200):
     state=app.snapshot(job)
     if state['status']!='running':break
     time.sleep(.01)
    self.assertEqual(state['status'],'done',state);self.assertEqual(state['results'],{'0':'看见。','1':'我能问一下吗？'})
    with app.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM translations').fetchone()[0],2)
   finally:
    release.set();app.pool.shutdown();app.local_engine.close(cleanup=True);app.antigravity.close(cleanup=True)

 def test_numbered_outputs_are_mapped_by_identity_not_object_order(self):
  self.assertEqual(parse_translation('{"translations":{"9":"下一句","7":"看见"}}',2,[7,9]),['看见','下一句'])
  for raw in ['{"translations":{"7":"看见"}}','{"translations":{"7":"看见","9":"下一句","8":"额外"}}','{"translations":["看见","下一句"]}']:
   with self.assertRaises(AppError):parse_translation(raw,2,[7,9])
 def test_partial_json_requires_complete_escaped_string_and_delimiter(self):
  raw=json.dumps({'translations':{'7':'看到“它”，并说："你好"。','9':'下一句'}},ensure_ascii=False)
  expected={'7':'看到“它”，并说："你好"。','9':'下一句'}
  for end in range(len(raw)+1):
   got=policy.partial_captions(raw[:end],[7,9])
   self.assertTrue(all(expected[k]==v for k,v in got.items()),(end,got))
  self.assertEqual(policy.partial_captions(raw,[7,9]),expected)
  self.assertEqual(policy.partial_captions('{"translations":{"999":"不属于当前字幕",',[7,9]),{})
 def test_caption_prompt_and_schema_use_stable_ids_without_parallel_arrays(self):
  prompt,payload=policy.build_request('Video',['to see.','Can I ask you'],[],{'mode':'captions','paragraph_ids':[7,8],'following_context':['the next line']})
  self.assertEqual(payload['segments'],[{'id':'7','text':'to see.'},{'id':'8','text':'Can I ask you'}])
  self.assertNotIn('paragraphs',payload)
  schema=policy.output_schema(payload)['properties']['translations']
  self.assertEqual(schema['required'],['7','8']);self.assertFalse(schema['additionalProperties'])
  self.assertIn('不要先合并整段',prompt)
 def test_news_cache_and_schema_unchanged_by_caption_revision(self):
  from unittest.mock import patch
  options=policy.normalize_options({},['English'])
  before={kind:policy.cache_keys(kind,'Title',['English'],'page','chatgpt','m',options) for kind in ['news','captions']}
  with patch.object(policy,'CAPTION_VERSION','new-caption-version'):
   self.assertEqual(before['news'],policy.cache_keys('news','Title',['English'],'page','chatgpt','m',options))
   self.assertNotEqual(before['captions'],policy.cache_keys('captions','Title',['English'],'page','chatgpt','m',options))
  self.assertIs(policy.output_schema({'paragraphs':['English']}),policy.OUTPUT_SCHEMA)

if __name__=='__main__':unittest.main()
