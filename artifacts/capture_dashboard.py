"""Capture both dashboard tabs with Playwright after Plotly finishes rendering."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

out=Path('artifacts/visual-review');out.mkdir(parents=True,exist_ok=True)
prefix=sys.argv[1] if len(sys.argv)>1 else 'review'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    page.goto('http://localhost:8501')
    page.get_by_role('tab',name='Executive summary',exact=True).wait_for(timeout=40000)
    page.wait_for_function("() => document.querySelectorAll('.js-plotly-plot').length >= 12 && [...document.querySelectorAll('.js-plotly-plot')].every(e => e._fullLayout)",timeout=40000)
    index=0
    for tab in ['Executive summary','Stock control & supplier reliability']:
        page.get_by_role('tab',name=tab,exact=True).click()
        panel=page.get_by_role('tabpanel').filter(visible=True)
        page.screenshot(path=str(out/f'{prefix}-{index:02}-top.png'))
        charts=panel.locator('[data-testid="stPlotlyChart"]')
        for i in range(charts.count()):
            charts.nth(i).screenshot(path=str(out/f'{prefix}-{index:02}.png'))
            index+=1
    print('charts',index)
    print('exceptions',page.locator('[data-testid="stException"]').all_text_contents())
    browser.close()
