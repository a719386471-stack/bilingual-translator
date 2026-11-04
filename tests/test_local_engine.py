import queue
from pathlib import Path
import sys
import unittest
import threading
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_engine import LocalEngine, EngineError
from youtube_captions import CaptionStore, CaptionsError


class LocalEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine=LocalEngine()

    def tearDown(self):
        self.engine.close(cleanup=True)

    def test_api_key_billing_is_rejected(self):
        self.engine.start=lambda:None
        self.engine.rpc=lambda *args,**kwargs:{'account':{'type':'apiKey'}}
        with self.assertRaises(EngineError):
            self.engine.account()

    def test_ephemeral_translation_completion(self):
        self.engine.account=lambda:{'type':'chatgpt'}
        self.engine.reasoning_options={'test':{'low','high'}}
        calls=[]
        def rpc(method,params,**kwargs):
            calls.append((method,params))
            if method=='thread/start':
                return {'thread':{'id':'test-thread'}}
            if method=='turn/start':
                self.engine.events.put({'method':'item/completed','params':{'threadId':'test-thread','item':{'id':'message','type':'agentMessage','text':'{"translations":["中文"]}'}}})
                self.engine.events.put({'method':'thread/tokenUsage/updated','params':{'threadId':'test-thread','tokenUsage':{'total':{'inputTokens':100,'outputTokens':10,'totalTokens':110,'cachedInputTokens':60,'reasoningOutputTokens':0}}}})
                self.engine.events.put({'method':'turn/completed','params':{'threadId':'test-thread','turn':{'status':'completed'}}})
            return {}
        self.engine.rpc=rpc
        usage=[]
        result=self.engine.translate('Translate only.',{'paragraphs':['English']},'test',on_usage=usage.append)
        self.assertEqual(result,'{"translations":["中文"]}')
        self.assertEqual(usage,[{'input':100,'output':10,'total':110,'cached':60,'reasoning':0}])
        self.assertTrue(calls[0][1]['ephemeral'])
        self.assertEqual(calls[0][1]['modelProvider'],'openai')
        self.assertEqual(calls[0][1]['sandbox'],'read-only')
        self.assertEqual(calls[0][1]['approvalPolicy'],'never')
        self.assertEqual(calls[-1][0],'thread/unsubscribe')
        self.assertEqual(next(params for method,params in calls if method=='turn/start')['effort'],'low')

    def test_unexpected_tools_are_not_accepted_as_translation(self):
        self.engine.account=lambda:{'type':'chatgpt'}
        def rpc(method,params,**kwargs):
            if method=='thread/start':return {'thread':{'id':'test-thread'}}
            if method=='turn/start':
                self.engine.events.put({'method':'item/completed','params':{'threadId':'test-thread','item':{'type':'commandExecution'}}})
            return {}
        self.engine.rpc=rpc
        with self.assertRaises(EngineError):
            self.engine.translate('Translate only.',{'paragraphs':['English']},'test')

    def test_caption_delta_is_delivered_before_turn_completion(self):
        self.engine.account=lambda:{'type':'chatgpt'}
        seen=[];schemas=[]
        def rpc(method,params,**kwargs):
            if method=='thread/start':return {'thread':{'id':'stream-thread'}}
            if method=='turn/start':
                schemas.append(params['outputSchema'])
                for chunk in ['{"translations":{"7":"看见。",','"8":"我能问一下吗？"}}']:
                    self.engine.events.put({'method':'item/agentMessage/delta','params':{'threadId':'stream-thread','itemId':'m','delta':chunk}})
                self.engine.events.put({'method':'item/completed','params':{'threadId':'stream-thread','item':{'id':'m','type':'agentMessage','text':'{"translations":{"7":"看见。","8":"我能问一下吗？"}}'}}})
                self.engine.events.put({'method':'turn/completed','params':{'threadId':'stream-thread','turn':{'status':'completed'}}})
            return {}
        self.engine.rpc=rpc
        result=self.engine.translate('Translate.',{'segments':[{'id':'7','text':'to see.'},{'id':'8','text':'Can I ask?'}]},'test',on_text=seen.append)
        self.assertEqual(seen[0],'{"translations":{"7":"看见。",')
        self.assertEqual(seen[-1],result)
        self.assertEqual(schemas[0]['properties']['translations']['required'],['7','8'])

    def test_cancel_interrupts_the_actual_turn_before_unsubscribe(self):
        cancel=threading.Event();calls=[]
        self.engine.account=lambda:{'type':'chatgpt'}
        def rpc(method,params,**kwargs):
            calls.append((method,params))
            if method=='thread/start':return {'thread':{'id':'temporary-thread'}}
            if method=='turn/start':cancel.set();return {'turn':{'id':'temporary-turn'}}
            return {}
        self.engine.rpc=rpc
        with self.assertRaises(EngineError):self.engine.translate('Translate.',{},'test',cancel=cancel)
        self.assertEqual(calls[-2],('turn/interrupt',{'threadId':'temporary-thread','turnId':'temporary-turn'}))
        self.assertEqual(calls[-1][0],'thread/unsubscribe')


class CaptionBoundaryTests(unittest.TestCase):
    def test_only_video_ids_accepted(self):
        store=CaptionStore()
        with patch('youtube_captions.YouTubeTranscriptApi') as api:
            for value in ['http://127.0.0.1/private','../../../etc/passwd','short',None]:
                with self.assertRaises(CaptionsError):store.fetch(value)
            api.assert_not_called()


if __name__=='__main__':unittest.main()
