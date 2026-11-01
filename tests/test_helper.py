import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import helper
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = helper.App(self.temp.name)

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.app.local_engine.close(cleanup=True)
        self.app.antigravity.close(cleanup=True)
        self.temp.cleanup()

    def test_registration_pkce_state_and_replay(self):
        url = self.app.begin_auth()
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['client_id'], ['dynamic_agent_client'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        host = query['ext_agent_host_id']
        self.assertEqual(parse_qs(urlsplit(self.app.begin_auth()).query)['ext_agent_host_id'], host)
        with self.assertRaises(helper.AppError):
            self.app.finish_auth({'state':'wrong', 'code':'x'})
        state = query['state'][0]
        with self.assertRaises(helper.AppError):
            self.app.finish_auth({'state':state,'error':'access_denied'})
        self.assertNotIn(state, self.app.pending)

    def complete_auth(self, bad=False):
        query = parse_qs(urlsplit(self.app.begin_auth()).query)
        private = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims = {'iss':helper.AUTH,'aud':'oaiapp_test','sub':'subject','exp':time.time()+600,
                  'iat':time.time(),'nonce':query['nonce'][0],'email':'test@example.invalid'}
        signed = jwt.encode(claims,private,algorithm='RS256')
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048).public_key() if bad else private.public_key()
        class Key:
            pass
        obj = Key(); obj.key = key
        with patch.object(self.app.jwks,'get_signing_key_from_jwt',return_value=obj), patch('helper.remote_json', return_value={
            'id_token':signed, 'access_token':'fake', 'refresh_token':'fake_refresh', 'scope':helper.SCOPES, 'expires_in':600}):
            self.app.finish_auth({'state':query['state'][0],'code':'sample','client_id':'oaiapp_test'})

    def test_valid_login_and_protected_storage(self):
        self.complete_auth()
        self.assertTrue(self.app.status()['connected'])
        self.assertEqual(self.app.path.stat().st_mode & 0o777,0o600)
        self.assertNotIn('access_token',json.dumps(self.app.status()))

    def test_invalid_signature_not_saved(self):
        with self.assertRaises(helper.AppError):
            self.complete_auth(True)
        self.assertIsNone(self.app.account())
        # A failed identity validation must not discard the already issued client.
        self.assertEqual(self.app.config['pending_client'], 'oaiapp_test')
        query = parse_qs(urlsplit(self.app.begin_auth()).query)
        self.assertEqual(query['client_id'], ['oaiapp_test'])
        self.assertNotIn('agent_name_hint', query)

    def test_cache_and_batches(self):
        paragraphs = ['A report paragraph %d with enough words.' % i for i in range(14)]
        self.app.models = lambda *args:[{'slug':'test','display_name':'Test'}]
        calls = []
        def infer(title, paras, previous, model, **kwargs):
            calls.append(paras)
            kwargs['on_usage']({'input':100,'output':20,'total':120,'cached':50,'reasoning':5})
            return ['译文：'+p for p in paras]
        self.app.infer = infer
        payload = {'title':'News','paragraphs':paragraphs,'model':'test','pageKey':'a'*64}
        identifier = self.app.start_job(payload)
        self.wait_job(identifier)
        self.assertEqual(len(calls),3)
        self.assertEqual(self.app.usage.summary('a'*64)['page']['total'],360)
        self.assertEqual(len(self.app.snapshot(identifier)['results']),14)
        self.wait_job(self.app.start_job(payload))
        self.assertEqual(len(calls),3)
        self.assertEqual(self.app.usage.summary('a'*64)['page']['total'],360)
        payload['title']='Different context'
        self.wait_job(self.app.start_job(payload))
        self.assertEqual(len(calls),6)

    def test_cancel_does_not_publish_late_batch(self):
        self.app.models = lambda *args:[{'slug':'test'}]
        def infer(*args,**kwargs):
            kwargs['on_usage']({'input':100,'output':20,'total':120,'cached':0,'reasoning':0})
            job = next(iter(self.app.jobs.values()))
            job['cancel'].set()
            return ['迟到的译文']
        self.app.infer = infer
        identifier = self.app.start_job({'title':'News','paragraphs':['English article'], 'model':'test'})
        state = self.wait_job(identifier)
        self.assertEqual(state['status'],'cancelled')
        self.assertFalse(state['results'])
        self.assertEqual(self.app.usage.summary()['today']['total'],120)

    def wait_job(self, identifier):
        for _ in range(200):
            state=self.app.snapshot(identifier)
            if state['status']!='running':
                self.assertNotEqual(state['status'],'error',state.get('error'))
                return state
            time.sleep(.01)
        self.fail('job timed out')

    def test_provider_cache_and_usage_do_not_mix(self):
        self.app.models=lambda *args:[{'slug':'same-model'}]
        calls=[]
        def infer(title,paras,previous,model,**kw):
            calls.append(kw['provider'])
            kw['on_usage']({'input':10,'output':5,'total':15,'cached':0,'reasoning':0,'estimated':kw['provider']=='antigravity'})
            return ['示例译文']
        self.app.infer=infer
        payload={'model':'same-model','title':'News','paragraphs':['An English news article.']}
        self.wait_job(self.app.start_job(payload))
        self.app.config['provider']='antigravity'
        self.wait_job(self.app.start_job(payload))
        self.app.config['provider']='chatgpt'
        self.wait_job(self.app.start_job(payload))
        self.assertEqual(calls,['chatgpt','antigravity'])
        total=self.app.usage.summary()['today']
        self.assertEqual(total['total'],15)
        self.assertEqual(total['estimated_total'],15)

    def test_explicit_page_provider_survives_global_switch(self):
        self.app.config['provider']='antigravity'
        self.app.models=lambda *args:[{'slug':'test'}]
        seen=[]
        def infer(*args,**kw):seen.append(kw['provider']);return ['中文']
        self.app.infer=infer
        self.wait_job(self.app.start_job({'title':'News','model':'test','provider':'chatgpt','paragraphs':['English paragraph']}))
        self.assertEqual(seen,['chatgpt'])


class ContractTests(unittest.TestCase):
    def test_sse_completion_and_truncation(self):
        events = [{'type':'response.output_text.delta','delta':'{"translations":["中文"]}'}, {'type':'response.completed'}]
        stream=io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode())
        self.assertEqual(helper.parse_translation(helper.stream_text(stream),1),['中文'])
        with self.assertRaises(helper.AppError):
            helper.stream_text(io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'))

    def test_late_limit_error_and_misalignment(self):
        with self.assertRaises(helper.AppError):
            helper.stream_text(io.BytesIO(b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n'))
        for text in ['{"translations":["only one"]}', '{"translations":["a",""]}', 'not json']:
            with self.assertRaises(helper.AppError):
                helper.parse_translation(text,2)

    def test_origin_boundaries(self):
        self.assertTrue(helper.Handler.allowed_origin('chrome-extension://'+'a'*32))
        for origin in ['https://evil.invalid','null',helper.BASE+'.evil.invalid','chrome-extension://bad']:
            self.assertFalse(helper.Handler.allowed_origin(origin))


if __name__=='__main__':
    unittest.main()
