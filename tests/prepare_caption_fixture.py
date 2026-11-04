"""Build a standalone local renderer regression page; no model or account access."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(out,sample=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'extension/youtube.js').read_text().replace("mode:'closed'","mode:'open'")
    source=source.replace("!/(^|\\.)youtube\\.com$/.test(location.hostname)","location.hostname!=='127.0.0.1'")
    source=source.replace('  function sourceLabel()', '  globalThis.__fixtureGroup=groupRollingCues;\n  function sourceLabel()')
    html='''<!doctype html><meta charset="utf-8"><title>Caption renderer regression checks</title><style>body{font:16px sans-serif;background:#eaf2ed}#movie_player{position:relative;width:960px;height:540px;background:#243b30}video{width:100%;height:100%}pre{white-space:pre-wrap}</style><div id="movie_player"><video></video></div><pre id="result">Running…</pre>'''
    if sample:html+='<script>window.captionSample='+json.dumps(json.loads(Path(sample).read_text()),ensure_ascii=True).replace('<','\\u003c')+';</script>'
    html+='<script>window.loadCaptionScript=async()=>{const s=document.createElement("script");s.textContent='+json.dumps(source).replace('<','\\u003c')+';document.body.append(s);};</script>'
    html+='<script>'+(ROOT/'tests/caption_browser_fixture.js').read_text()+'</script>'
    (out/'index.html').write_text(html)
    return out/'index.html'
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--sample',type=Path)
    args=parser.parse_args();print(build(args.out,args.sample))
