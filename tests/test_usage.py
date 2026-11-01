from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
import sqlite3

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from usage_store import UsageStore


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'ledger.sqlite'
        self.store=UsageStore(self.path)
        self.counts={'input':100,'output':20,'total':120,'cached':60,'reasoning':5}
        self.before=datetime(2026,10,31,15,59,tzinfo=timezone.utc).timestamp()
        self.after=datetime(2026,10,31,16,1,tzinfo=timezone.utc).timestamp()

    def tearDown(self):
        self.temp.cleanup()

    def test_page_daily_and_unknown_requests(self):
        self.store.record('1','a',self.counts,now=self.before)
        self.store.record('2','b',self.counts,now=self.before)
        self.store.record('3','a',now=self.before)
        value=self.store.summary('a',now=self.before)
        self.assertEqual(value['page']['total'],120)
        self.assertEqual(value['today']['total'],240)
        self.assertEqual(value['page']['unreported'],1)
        self.assertEqual(value['today']['cached'],120)  # Already included in input.

    def test_duplicate_updates_do_not_double_count_or_move_day(self):
        self.store.record('1','a',now=self.before)
        self.store.record('1','a',self.counts,now=self.before)
        self.store.record('1','b',self.counts,now=self.after)
        self.store.record('1','a',now=self.after)
        value=UsageStore(self.path).summary('a',now=self.before)
        self.assertEqual(value['page']['total'],120)
        self.assertEqual(value['today']['requests'],1)
        self.assertEqual(value['today']['unreported'],0)
        self.assertEqual(self.store.summary('b',now=self.after)['page']['total'],0)

    def test_singapore_midnight_and_persistence(self):
        self.store.record('1','a',self.counts,now=self.before)
        self.store.record('2','a',self.counts,now=self.after)
        value=UsageStore(self.path).summary('a',now=self.after)
        self.assertEqual(value['day'],'2026-11-01')
        self.assertEqual(value['today']['total'],120)
        self.assertEqual(value['page']['total'],240)

    def test_missing_or_invalid_counts_are_not_zero_usage(self):
        self.store.record('1','a',{'total':10},now=self.before)
        self.store.record('2','a',{**self.counts,'input':-5},now=self.before)
        value=self.store.summary('a',now=self.before)['page']
        self.assertEqual(value['total'],0)
        self.assertEqual(value['unreported'],2)

    def test_estimates_separate_and_official_counts_replace_them(self):
        self.store.record('1','a',{**self.counts,'estimated':True},now=self.before,provider='antigravity')
        value=self.store.summary('a',now=self.before)['page']
        self.assertEqual(value['total'],0)
        self.assertEqual(value['estimated_total'],120)
        self.assertEqual(value['unreported'],0)
        self.store.record('1','a',self.counts,now=self.after)
        value=self.store.summary('a',now=self.before)['page']
        self.assertEqual(value['total'],120)
        self.assertEqual(value['estimated_total'],0)
        self.assertEqual(value['requests'],1)

    def test_session_page_and_today_are_independently_counted(self):
        self.store.record('1','a',self.counts,now=self.before,session_id='one')
        self.store.record('2','a',{**self.counts,'estimated':True},now=self.before,session_id='two')
        self.store.record('3','b',now=self.before,session_id='one')
        first=self.store.summary('a',now=self.before,session_id='one')
        second=self.store.summary('a',now=self.before,session_id='two')
        self.assertEqual(first['session']['total'],120)
        self.assertEqual(first['session']['unreported'],0)
        self.assertEqual(first['page']['total'],120)
        self.assertEqual(first['page']['estimated_total'],120)
        self.assertEqual(first['today']['unreported'],1)
        self.assertEqual(second['session']['total'],0)
        self.assertEqual(second['session']['estimated_total'],120)
        self.assertEqual(self.store.summary('a',now=self.before)['session']['requests'],0)

    def test_old_records_remain_in_page_and_day_but_not_new_session(self):
        self.store.record('old','a',self.counts,now=self.before)
        self.store.record('new','a',self.counts,now=self.before,session_id='new-session')
        result=UsageStore(self.path).summary('a',now=self.before,session_id='new-session')
        self.assertEqual(result['session']['total'],120)
        self.assertEqual(result['page']['total'],240)
        self.assertEqual(result['today']['total'],240)

    def test_migrates_original_database_without_losing_usage(self):
        path=self.path.parent/'old.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE token_usage (request_id TEXT PRIMARY KEY,page_key TEXT NOT NULL,day TEXT NOT NULL,created REAL NOT NULL,input INTEGER,output INTEGER,total INTEGER,cached INTEGER,reasoning INTEGER)')
            db.execute('INSERT INTO token_usage VALUES (?,?,?,?,?,?,?,?,?)',('legacy','a','2026-10-31',self.before,100,20,120,60,5))
        upgraded=UsageStore(path).summary('a',now=self.before,session_id='new-session')
        self.assertEqual(upgraded['page']['total'],120)
        self.assertEqual(upgraded['session']['total'],0)
        self.assertEqual(upgraded['page']['requests'],1)


if __name__=='__main__':unittest.main()
