"""Isolated frontend payload tests: article context and independent story groups."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
script=(ROOT/'extension/content.js').read_text()
fixtures=[
 ('https://www.wsj.com/', '''<main><article><h3><a data-testid="flexcard-headline" href="/finance/central-bank-interest">Interest is rising at the central bank</a></h3><div><a aria-hidden="true" href="/finance/central-bank-interest?mod=hp"><p data-testid="flexcard-text">The bank raised its lending rate on Tuesday.</p></a></div><p data-testid="Byline">By News Author</p></article><article><h3><a data-testid="flexcard-headline" href="/arts/interest-in-art">Interest in art is growing among children</a></h3><p data-testid="flexcard-text">Museums report more family visitors this year.</p></article><nav><a data-testid="flexcard-headline" href="/news/navigation">Navigation should not become a news story</a></nav></main>''', 'feed', [0,0,1,1]),
 ('https://www.reuters.com/world/', '''<main><h1>World news</h1><article><h3><a data-testid="Heading" href="/business/bank-raises-interest-2026-11-01/?utm=home">Bank raises interest as inflation remains high</a></h3><p data-testid="Description">The central bank signalled more tightening ahead.</p><p class="byline">By Financial Reporter</p></article><article><h3><a data-testid="Heading" href="/world/children-show-interest-in-art-2026-11-01/">Children show interest in a new art museum</a></h3><p data-testid="Description">The museum welcomed thousands of young visitors.</p></article><p>This category introduction is not part of either story.</p><aside data-testid="advertisement"><h3><a href="/world/paid-advertisement-2026-11-01/">Sponsored headline must stay excluded</a></h3><p>This is an advertisement description.</p></aside></main>''', 'feed', [0,0,1,1]),
 ('https://www.reuters.com/business/bank-raises-interest-2026-11-01/', '''<meta property="og:type" content="article"><h1>Central bank raises interest rates</h1><div data-testid="ArticleBody"><div data-testid="paragraph-0">The central bank raised its benchmark interest rate.</div><div data-testid="paragraph-1">Officials said the bank was committed to fighting inflation.</div></div><main><h2><a href="/world/another-story-2026-11-01/">Another unrelated story linked by the article</a></h2><h2><a href="/world/third-story-2026-11-01/">A third story is also related reading</a></h2></main>''', 'article', [0,0,0]),
 ('https://www.wsj.com/business/test-article', '''<article><h1>Investors weigh the latest earnings results</h1><div class="paywall"><p>Investors showed strong interest in the company's shares.</p><p>The company's interest expenses rose last quarter.</p></div></article>''', 'article', [0,0,0]),
 ('https://news.example.com/', '''<main><article><h3><a href="/story/one">First independent article headline</a></h3><p>The first story has its own explanatory summary.</p></article><article><h3><a href="/story/two">Second independent article headline</a></h3><p>The second story has a different explanatory summary.</p></article></main>''', 'feed', [0,0,1,1]),
]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,channel='chromium')
 page=browser.new_page()
 for url,body,mode,mapping in fixtures:
  page.route(url,lambda route,request,body=body:route.fulfill(content_type='text/html',body='<html><meta charset="utf-8"><body>'+body+'</body></html>'))
  page.goto(url)
  page.evaluate('''() => {window.captured=[];window.chrome={runtime:{id:'fixture-extension',onMessage:{addListener(fn){window.listener=fn}}}};window.__cgptBridge={raw:async()=>({}),run:async(payload)=>window.captured.push(payload)}}''')
  page.add_script_tag(content=script)
  result=page.evaluate('''() => new Promise(resolve=>window.listener({action:'translate',model:'fixture-model'},{id:'fixture-extension'},resolve))''')
  assert result['ok'],(url,result)
  page.wait_for_function('window.captured.length===1')
  data=page.evaluate('window.captured[0]')
  assert data['newsMode']==mode,(url,data)
  assert len(data['paragraphs'])==len(mapping),(url,data)
  assert len(data['groups'])==len(data['paragraphs'])
  for i in range(len(mapping)):
   for j in range(len(mapping)):
    assert (data['groups'][i]==data['groups'][j])==(mapping[i]==mapping[j]),(url,data)
  assert not any('By News Author' in x or 'Reporter' in x or 'advertisement' in x or 'Navigation' in x or 'category introduction' in x for x in data['paragraphs']),data
  if mode=='feed':
   assert all(g.startswith('story:https://') for g in data['groups']),data
   assert all('?' not in g and '#' not in g for g in data['groups']),data
 browser.close()
print('PASS: WSJ and Reuters cards grouped by canonical story; unrelated cards isolated; article body retained; bylines/nav/ads excluded; generic cards supported')
