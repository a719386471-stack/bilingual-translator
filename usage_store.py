"""Local official/estimated token ledger; no titles or page URLs."""
from datetime import datetime
import math
import re
import sqlite3
import time
from zoneinfo import ZoneInfo

ZONE=ZoneInfo('Asia/Singapore')
FIELDS=('input','output','total','cached','reasoning')


def estimate_text_tokens(text):
    """Visible-text heuristic only; never estimates hidden prompts or reasoning."""
    han=len(re.findall(r'[\u3400-\u9fff]',text))
    ascii_count=sum(ord(c)<128 for c in text)
    other=len(text)-han-ascii_count
    return math.ceil(ascii_count/4+han*1.5+other/2)


class UsageStore:
    def __init__(self,path):
        self.path=str(path)
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS token_usage (
                request_id TEXT PRIMARY KEY,page_key TEXT NOT NULL,day TEXT NOT NULL,
                created REAL NOT NULL,input INTEGER,output INTEGER,total INTEGER,cached INTEGER,reasoning INTEGER)''')
            columns={r[1] for r in db.execute('PRAGMA table_info(token_usage)')}
            for name,kind in [('provider',"TEXT NOT NULL DEFAULT 'chatgpt'"),('estimated_input','INTEGER'),('estimated_output','INTEGER'),('estimated_total','INTEGER'),('session_id',"TEXT NOT NULL DEFAULT ''")]:
                if name not in columns:db.execute('ALTER TABLE token_usage ADD COLUMN '+name+' '+kind)
            db.execute('CREATE INDEX IF NOT EXISTS usage_day ON token_usage(day)')
            db.execute('CREATE INDEX IF NOT EXISTS usage_page ON token_usage(page_key)')
            db.execute('CREATE INDEX IF NOT EXISTS usage_session ON token_usage(session_id,page_key)')

    def db(self):return sqlite3.connect(self.path,timeout=15)

    def record(self,request_id,page_key,usage=None,now=None,provider='chatgpt',session_id=''):
        now=time.time() if now is None else now
        day=datetime.fromtimestamp(now,ZONE).date().isoformat()
        values=[None]*5;estimated=[None]*3
        valid=isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in FIELDS)
        if valid:
            if usage.get('estimated'):estimated=[usage[k] for k in ('input','output','total')]
            else:values=[usage[k] for k in FIELDS]
        with self.db() as db:
            db.execute('''INSERT INTO token_usage(request_id,page_key,day,created,input,output,total,cached,reasoning,provider,estimated_input,estimated_output,estimated_total,session_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET
                input=COALESCE(excluded.input,token_usage.input),output=COALESCE(excluded.output,token_usage.output),
                total=COALESCE(excluded.total,token_usage.total),cached=COALESCE(excluded.cached,token_usage.cached),reasoning=COALESCE(excluded.reasoning,token_usage.reasoning),
                estimated_input=CASE WHEN excluded.total IS NOT NULL OR token_usage.total IS NOT NULL THEN NULL ELSE COALESCE(excluded.estimated_input,token_usage.estimated_input) END,
                estimated_output=CASE WHEN excluded.total IS NOT NULL OR token_usage.total IS NOT NULL THEN NULL ELSE COALESCE(excluded.estimated_output,token_usage.estimated_output) END,
                estimated_total=CASE WHEN excluded.total IS NOT NULL OR token_usage.total IS NOT NULL THEN NULL ELSE COALESCE(excluded.estimated_total,token_usage.estimated_total) END''',
                (request_id,page_key,day,now,*values,provider,*estimated,session_id))

    def summary(self,page_key='',now=None,session_id=''):
        day=datetime.fromtimestamp(time.time() if now is None else now,ZONE).date().isoformat()
        def aggregate(db,condition,values):
            names=(*FIELDS,'estimated_input','estimated_output','estimated_total')
            row=db.execute('SELECT '+','.join('COALESCE(SUM('+k+'),0)' for k in names)+
                ',COUNT(*),SUM(CASE WHEN total IS NULL AND estimated_total IS NULL THEN 1 ELSE 0 END) FROM token_usage WHERE '+condition,values).fetchone()
            return dict(zip((*names,'requests','unreported'),[x or 0 for x in row]))
        with self.db() as db:
            return {'session':aggregate(db,"session_id=? AND page_key=? AND session_id<>''",(session_id,page_key)),
                    'page':aggregate(db,'page_key=?',(page_key,)), 'today':aggregate(db,'day=?',(day,)),
                    'day':day,'timezone':'Asia/Singapore'}
