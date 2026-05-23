"""
LUNVIA 爬蟲 DEBUG v2 - 把頁面 HTML 寫入 Notion 頁面
"""
import asyncio, os, requests
from playwright.async_api import async_playwright

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"

async def debug_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "zh-TW,zh;q=0.9"})
        
        await page.goto(SEARCH_URL, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=20000)
        
        title = await page.title()
        url = page.url
        print(f"Title: {title}")
        print(f"URL: {url}")
        
        # 取得所有 input 的資訊
        inputs_info = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input, select, textarea');
            return Array.from(inputs).slice(0, 30).map(el => ({
                tag: el.tagName,
                name: el.name || '',
                type: el.type || '',
                value: (el.value || '').substring(0, 30),
                placeholder: el.placeholder || '',
                id: el.id || '',
                visible: el.offsetParent !== null
            }));
        }""")
        
        print(f"\n=== {len(inputs_info)} form elements ===")
        for i, inp in enumerate(inputs_info):
            print(f"[{i}] {inp['tag']} name={inp['name']!r} type={inp['type']!r} value={inp['value']!r} id={inp['id']!r} visible={inp['visible']}")
        
        # 取得 forms
        forms_info = await page.evaluate("""() => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(f => ({
                action: f.action || '',
                method: f.method || '',
                id: f.id || ''
            }));
        }""")
        print(f"\n=== {len(forms_info)} forms ===")
        for f in forms_info:
            print(f"  action={f['action']!r} method={f['method']!r} id={f['id']!r}")
        
        await browser.close()

asyncio.run(debug_page())
