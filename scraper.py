"""
LUNVIA 標案爬蟲 DEBUG 版 - 列出頁面所有 input 元素
"""

import asyncio
from playwright.async_api import async_playwright

SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"

async def debug_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "zh-TW,zh;q=0.9"})
        
        print(f"Navigating to {SEARCH_URL}...")
        await page.goto(SEARCH_URL, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=20000)
        
        print(f"Page title: {await page.title()}")
        print(f"Page URL: {page.url}")
        
        # 列出所有 input
        inputs = await page.query_selector_all("input")
        print(f"\n=== 找到 {len(inputs)} 個 input 元素 ===")
        for i, inp in enumerate(inputs[:30]):
            name = await inp.get_attribute("name") or ""
            type_ = await inp.get_attribute("type") or ""
            value = await inp.get_attribute("value") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            cls = await inp.get_attribute("class") or ""
            visible = await inp.is_visible()
            print(f"[{i}] name={name!r} type={type_!r} value={value[:20]!r} placeholder={placeholder!r} visible={visible}")
        
        # 列出所有 form
        forms = await page.query_selector_all("form")
        print(f"\n=== 找到 {len(forms)} 個 form 元素 ===")
        for i, form in enumerate(forms[:5]):
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            print(f"[{i}] action={action!r} method={method!r}")
        
        # 列出所有 textarea
        textareas = await page.query_selector_all("textarea")
        print(f"\n=== 找到 {len(textareas)} 個 textarea ===")
        
        # 列出所有可見的文字輸入
        print("\n=== 可見的文字輸入 ===")
        all_inputs = await page.query_selector_all("input:visible")
        for inp in all_inputs[:10]:
            name = await inp.get_attribute("name") or ""
            type_ = await inp.get_attribute("type") or "text"
            print(f"  name={name!r} type={type_!r}")
        
        await browser.close()

asyncio.run(debug_page())
