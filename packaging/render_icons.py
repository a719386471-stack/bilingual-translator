from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
svg=(root/'logo.svg').read_text()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page(device_scale_factor=1)
 for size in [16,32,48,128]:
  page.set_viewport_size({'width':size,'height':size})
  page.set_content('<style>html,body{margin:0;background:transparent}svg{width:100vw;height:100vh;display:block}</style>'+svg)
  page.screenshot(path=str(root/'extension/icons'/f'icon-{size}.png'),omit_background=True)
 b.close()
print('Rendered 16,32,48,128 PNG from current logo.svg')
