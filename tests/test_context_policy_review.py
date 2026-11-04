"""Behavioral context/cache regressions; isolated data, no real model requests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import helper
import translation_policy as policy


class ContextPolicyReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = helper.App(self.temp.name)
        self.app.models = lambda *args: [{'slug': 'fixture'}]
        self.app.retry_wait = lambda job, seconds: job['cancel'].is_set()
        self.calls = []

        def infer(title, paragraphs, previous, model, **kwargs):
            self.calls.append({'paragraphs': list(paragraphs), 'previous': previous,
                               'reference': kwargs.get('reference', {})})
            return ['译文：' + text for text in paragraphs]
        self.app.infer = infer

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.app.local_engine.close(cleanup=True)
        self.app.antigravity.close(cleanup=True)
        self.temp.cleanup()

    def wait(self, identifier):
        for _ in range(600):
            state = self.app.snapshot(identifier)
            if state['status'] != 'running':
                return state
            time.sleep(.005)
        self.fail('Isolated translation job did not terminate')

    def run_job(self, **kwargs):
        payload = {'title': 'Fixture article', 'model': 'fixture', 'provider': 'chatgpt',
                   'pageKey': 'a' * 64, 'paragraphs': ['An English article paragraph.']}
        payload.update(kwargs)
        return self.wait(self.app.start_job(payload))

    def assert_done(self, state):
        self.assertEqual(state['status'], 'done', state.get('error'))

    def test_legacy_cache_cannot_bypass_new_rules(self):
        title, paragraphs = 'Fixture article', ['An English article paragraph.']
        digest = hashlib.sha256(json.dumps([title, paragraphs], ensure_ascii=False).encode()).hexdigest()
        legacy = hashlib.sha256(json.dumps(['news-v1', 'fixture', digest, 0, paragraphs[0]],
                                          ensure_ascii=False).encode()).hexdigest()
        v2 = hashlib.sha256(json.dumps(['translation-v2', 'news', 'chatgpt', 'fixture',
                                      title, [], paragraphs[0]], ensure_ascii=False).encode()).hexdigest()
        with self.app.db() as db:
            for key in (legacy, v2):
                db.execute('INSERT INTO translations VALUES (?,?,?)',
                           (key, '旧规则的错误译文', time.time()))
        state = self.run_job()
        self.assert_done(state)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('旧规则', state['results']['0'])

    def test_policy_version_invalidates_but_current_cache_works_offline(self):
        self.assert_done(self.run_job())
        self.app.models = lambda *args: (_ for _ in ()).throw(AssertionError('cache must work offline'))
        self.assert_done(self.run_job())
        self.assertEqual(len(self.calls), 1)
        self.app.models = lambda *args: [{'slug': 'fixture'}]
        with patch.object(policy, 'POLICY_VERSION', policy.POLICY_VERSION + '-next'):
            self.assert_done(self.run_job())
        self.assertEqual(len(self.calls), 2)

    def test_article_cache_changes_with_distant_source_context(self):
        original = ['The interest was substantial.', 'The story concerns lending.']
        self.assert_done(self.run_job(paragraphs=original))
        self.assertEqual(self.calls[-1]['paragraphs'], original)
        changed = [original[0], 'The story concerns a public exhibition.']
        self.assert_done(self.run_job(paragraphs=changed))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1]['paragraphs'], changed)

    def test_partial_article_cache_miss_preserves_full_source_without_retranslating_hits(self):
        paragraphs = ['The Federal Reserve discussed interest rates.',
                      'The interest was substantial.',
                      'Officials were referring to the cost of borrowing.',
                      'They did not describe public enthusiasm for the proposal.']
        self.assert_done(self.run_job(paragraphs=paragraphs))
        self.assertEqual(len(self.calls), 1)
        options = policy.normalize_options({}, paragraphs)
        keys = policy.cache_keys('news', 'Fixture article', paragraphs, 'a' * 64,
                                 'chatgpt', 'fixture', options)
        with self.app.db() as db:
            db.execute('DELETE FROM translations WHERE key=?', (keys[1],))
        state = self.run_job(paragraphs=paragraphs)
        self.assert_done(state)
        self.assertEqual(len(self.calls), 2)
        retry = self.calls[-1]
        self.assertEqual(retry['paragraphs'], [paragraphs[1]])
        self.assertEqual(retry['reference']['paragraph_ids'], [1])
        expected_context = [{'id': i, 'text': text} for i, text in enumerate(paragraphs) if i != 1]
        self.assertEqual(retry['reference']['article_context'], expected_context)
        _, sent = policy.build_request('Fixture article', retry['paragraphs'],
                                       retry['previous'], retry['reference'])
        self.assertEqual(sent['article_context'], expected_context)
        self.assertEqual(sent['paragraph_ids'], [1])
        self.assertEqual(len(state['results']), len(paragraphs))

    def test_feed_cache_is_stable_per_story_and_never_carries_other_story_memory(self):
        original = ['Interest rose at the bank.', 'Interest rose at the bank.']
        self.assert_done(self.run_job(newsMode='feed', groups=['story:finance', 'story:art'],
                                     paragraphs=original))
        self.assertEqual(self.calls[0]['reference']['mode'], 'feed')
        self.assertEqual(self.calls[0]['reference']['story_groups'], [policy.digest(g)[:12] for g in ['story:finance', 'story:art']])
        self.assertEqual(self.calls[0]['previous'], [])
        self.assertFalse(self.calls[0]['reference'].get('following_context'))
        updated = ['An exhibition attracted greater public interest.', original[0]]
        self.assert_done(self.run_job(title='Homepage refreshed', newsMode='feed',
                                     groups=['story:art', 'story:finance'], paragraphs=updated))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1]['paragraphs'], updated[:1])
        self.assertEqual(self.calls[-1]['reference']['story_groups'], [policy.digest('story:art')[:12]])
        self.assertFalse(self.calls[-1]['reference'].get('terms'))
        self.assertFalse(self.calls[-1]['reference'].get('overview'))

    def test_caption_positions_distinguish_repeated_words_but_reuse_overlapping_windows(self):
        state = self.run_job(kind='captions', paragraphs=['Right.', 'Right.'], cueIds=[5, 20])
        self.assert_done(state)
        self.assertEqual(len(state['results']), 2)
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM translations').fetchone()[0], 2)
        self.assert_done(self.run_job(kind='captions', paragraphs=['Right.'], cueIds=[20],
                                     contextBefore=[{'en': 'Turn at the corner.', 'zh': '在拐角转弯。'}]))
        self.assertEqual(len(self.calls), 1)
        self.assert_done(self.run_job(kind='captions', paragraphs=['Right.'], cueIds=[30]))
        self.assertEqual(len(self.calls), 2)

    def test_feed_keeps_complete_cards_together_at_batch_boundary(self):
        paragraphs = [('Card %d has a headline.' % i) for i in range(11)]
        paragraphs += ['One story headline.', 'Its matching summary.']
        groups = ['story:' + str(i) for i in range(11)] + ['story:last', 'story:last']
        options = policy.normalize_options({'newsMode': 'feed', 'groups': groups}, paragraphs)
        batches = list(policy.plan_batches(range(len(paragraphs)), paragraphs, 'news', options))
        self.assertEqual(len(batches), 2)
        self.assertTrue(any(11 in batch and 12 in batch for batch in batches))

    def test_oversized_feed_card_tail_keeps_own_context(self):
        paragraphs = [('Story A paragraph %d ' % i) + 'x' * 480 for i in range(13)]
        paragraphs += ['Unrelated story B headline.', 'Unrelated story B summary.']
        groups = ['story:A'] * 13 + ['story:B'] * 2
        self.assert_done(self.run_job(newsMode='feed', groups=groups, paragraphs=paragraphs))
        tail = next(call for call in self.calls if paragraphs[12] in call['paragraphs'])
        self.assertTrue(tail['previous'], 'Split-card tail lost all earlier story context')
        self.assertTrue(all('Story A' in item['en'] for item in tail['previous']))

    def test_caption_memory_without_page_key_stays_with_its_own_video_scope(self):
        seen = []
        def infer(title, paragraphs, previous, model, **kwargs):
            seen.append(kwargs['reference'])
            if title == 'Video about Acme':
                kwargs['on_context']({'overview': '', 'terms': [
                    {'source': 'Acme', 'target': '艾克米', 'sense': '公司名称'}]})
            return ['已翻译'] * len(paragraphs)
        self.app.infer = infer
        self.assert_done(self.run_job(title='Video about Acme', kind='captions', pageKey='',
                                     cueIds=[0], paragraphs=['Acme announced a new product.']))
        self.assert_done(self.run_job(title='Unrelated video', kind='captions', pageKey='',
                                     cueIds=[0], paragraphs=['We walked along the river bank.']))
        self.assertFalse(seen[-1].get('terms'))

    def test_request_identity_includes_caption_context_and_position(self):
        payload = {'title': 'Video fixture', 'model': 'fixture', 'kind': 'captions',
                   'pageKey': 'b' * 64, 'paragraphs': ['Right.'], 'cueIds': [5],
                   'requestId': '1' * 32}
        self.assert_done(self.wait(self.app.start_job(payload)))
        for changed in ({'cueIds': [8]}, {'contextAfter': ['A financial statement follows.']},
                        {'contextBefore': [{'en': 'He turned.', 'zh': '他转过身。'}]}):
            with self.subTest(changed=changed), self.assertRaises(helper.AppError):
                self.app.start_job({**payload, **changed})

    def test_paid_retry_budget_survives_frontend_resume(self):
        attempts = []
        def failing(*args, **kwargs):
            attempts.append(1)
            kwargs['on_usage']({'input': 50, 'output': 20, 'total': 70,
                                'cached': 0, 'reasoning': 0})
            raise helper.AppError('Temporary transport loss', 'connection', True)
        self.app.infer = failing
        payload = {'title': 'Retry fixture', 'model': 'fixture', 'paragraphs': ['English source.'],
                   'pageKey': 'a' * 64, 'requestId': '2' * 32}
        state = self.wait(self.app.start_job(payload))
        self.assertEqual(state['status'], 'error')
        self.assertFalse(state['retryable'])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.app.usage.summary()['today']['total'], 140)
        state = self.wait(self.app.start_job({**payload, 'resume': True}))
        self.assertEqual(state['status'], 'error')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.app.usage.summary()['today']['requests'], 2)

    def test_quota_and_auth_do_not_retry(self):
        for index, code in enumerate(('quota', 'auth')):
            attempts = []
            def failing(*args, **kwargs):
                attempts.append(1)
                raise helper.AppError('Unavailable', code, False)
            self.app.infer = failing
            state = self.run_job(title='Error fixture ' + str(index))
            self.assertEqual(state['status'], 'error')
            self.assertEqual(state['errorCode'], code)
            self.assertEqual(len(attempts), 1)

    def test_cancelled_or_misaligned_results_do_not_commit_semantic_memory(self):
        def cancelled(*args, **kwargs):
            kwargs['on_context']({'overview': '应丢弃的背景', 'terms': []})
            next(iter(self.app.jobs.values()))['cancel'].set()
            return ['应丢弃的译文']
        self.app.infer = cancelled
        state = self.run_job(kind='captions', cueIds=[5])
        self.assertEqual(state['status'], 'cancelled')
        self.assertEqual(state['results'], {})
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM translation_context').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM translations').fetchone()[0], 0)
        def misaligned(*args, **kwargs):
            kwargs['on_context']({'overview': '也应丢弃的背景', 'terms': []})
            return ['First translation', 'Unexpected extra translation']
        self.app.infer = misaligned
        state = self.run_job(kind='captions', cueIds=[6])
        self.assertEqual(state['status'], 'error')
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM translation_context').fetchone()[0], 0)

    def test_long_article_learns_context_during_translation_without_extra_summary_call(self):
        paragraphs = [('The Federal Reserve kept interest rates unchanged. ' + str(i) + ' ' + 'x' * 2940)
                      for i in range(8)]
        def infer(title, batch, previous, model, **kwargs):
            self.calls.append({'paragraphs': list(batch), 'reference': kwargs['reference']})
            kwargs['on_context']({'overview': '美联储维持利率不变。', 'terms': [
                {'source': 'Federal Reserve', 'target': '美联储', 'sense': '美国中央银行'}]})
            return ['已翻译'] * len(batch)
        self.app.infer = infer
        state = self.run_job(paragraphs=paragraphs)
        self.assert_done(state)
        self.assertEqual(state['strategy'], 'long_article')
        self.assertEqual(len(self.calls), 5)  # Smaller first result, then normal long-article batches.
        self.assertEqual(sum(len(c['paragraphs']) for c in self.calls), len(paragraphs))
        self.assertFalse(self.calls[0]['reference'].get('terms'))
        self.assertEqual(self.calls[1]['reference']['terms'][0]['target'], '美联储')
        self.assertEqual(self.calls[1]['reference']['overview'], '美联储维持利率不变。')


if __name__ == '__main__':
    unittest.main()
