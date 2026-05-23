"""
LUNVIA 標案情報自動爬蟲
每天從台灣採購公報網抓取設計相關標案，AI 評分後存入 Notion

環境變數（GitHub Secrets）:
  ANTHROPIC_API_KEY  - Anthropic API Key
  NOTION_TOKEN       - Notion Integration Token
  NOTION_DATABASE_ID - 標案資料庫 ID (bcd72699-c046-4ee7-a78e-57c65e957b07)
"""

import asyncio, json, os, re, time
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import requests

KEYWORDS = [
    "視覺設計","品牌識別","品牌設計","視覺識別","CIS","識別系統",
    "包裝設計","包裝規劃","印刷品設計","刊物設計","出版品設計","年報設計",
    "展覽設計","展示設計","展覽規劃","策展","活動視覺","展場設計",
    "形象設計","形象規劃","推廣設計","宣傳設計","圖像設計","插畫",
    "LOGO設計","標誌設計","吉祥物設計","文宣設計","美編",
]

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
TW    = timezone(timedelta(hours=8))
TODAY = datetime.now(TW).strftime("%Y/%m/%d")
SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
MIN_SCORE  = 6


async def search_keyword(page, keyword):
    try:
        await page.goto(SEARCH_URL, timeout=30000)
        await page.wait_for_selector('input[name="Keyword"]', timeout=10000)
        await page.fill('input[name="Keyword"]', keyword)
        await page.click('input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=20000)
        rows = await page.query_selector_all("table tr")
        results = []
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 3: continue
            date_text = (await cells[0].inner_text()).strip()
            if TODAY not in date_text: continue
            name_el = await cells[1].query_selector("a")
            if not name_el: continue
            name   = (await name_el.inner_text()).strip()
            link   = await name_el.get_attribute("href") or ""
            unit   = (await cells[2].inner_text()).strip() if len(cells) > 2 else ""
            budget = (await cells[3].inner_text()).strip() if len(cells) > 3 else ""
            if link and not link.startswith("http"):
                link = "https://www.taiwanbuying.com.tw/" + link.lstrip("/")
            results.append({"name":name,"unit":unit,"budget":budget,"link":link,"date":date_text,"keyword":keyword})
        print(f"  [{keyword}] 找到 {len(results)} 筆")
        return results
    except Exception as e:
        print(f"  [{keyword}] 錯誤：{e}")
        return []


async def scrape_all():
    all_tenders, seen_names = [], set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "zh-TW,zh;q=0.9"})
        for kw in KEYWORDS:
            results = await search_keyword(page, kw)
            for item in results:
                if item["name"] not in seen_names:
                    seen_names.add(item["name"])
                    all_tenders.append(item)
            await asyncio.sleep(1.5)
        await browser.close()
    print(f"共找到 {len(all_tenders)} 筆不重複標案")
    return all_tenders


def evaluate_tender(tender):
    prompt = f"""你是LUNVIA設計工作室負責人，專精品牌視覺、包裝設計、識別設計，單人工作室規模。
請評估以下標案，只回傳JSON：
標案名稱：{tender['name']}
來源單位：{tender['unit']}
預算：{tender['budget']}
連結：{tender['link']}

{{"overall_score":數字1-10,"recommendation":"強烈建議/值得考慮/謹慎評估/不建議",
"budget_score":數字,"spec_score":數字,"fit_score":數字,"win_score":數字,
"admin_burden":"輕/中/重","tender_type":"視覺設計/品牌識別/展覽規劃/包裝設計/空間設計/綜合設計",
"budget_assessment":"合理/偏低/偏高/不明","summary":"30字摘要","risks":["風險1","風險2"]}}"""
    try:
        res = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01","Content-Type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":500,"messages":[{"role":"user","content":prompt}]},
            timeout=30)
        text = re.sub(r"```json|```","",res.json()["content"][0]["text"]).strip()
        return json.loads(text)
    except Exception as e:
        print(f"  評分失敗：{e}")
        return None


def save_to_notion(tender, score):
    nums = re.findall(r"\d+", tender.get("budget","").replace(",",""))
    budget_num = int(nums[0]) if nums else None
    props = {
        "標案名稱":{"title":[{"text":{"content":tender["name"][:200]}}]},
        "來源單位":{"rich_text":[{"text":{"content":tender["unit"][:200]}}]},
        "類型":{"select":{"name":score.get("tender_type","視覺設計")}},
        "AI綜合評分":{"number":score.get("overall_score")},
        "預算分數":{"number":score.get("budget_score")},
        "規格分數":{"number":score.get("spec_score")},
        "適配分數":{"number":score.get("fit_score")},
        "勝率分數":{"number":score.get("win_score")},
        "預算評估":{"select":{"name":score.get("budget_assessment","不明")}},
        "投標建議":{"select":{"name":score.get("recommendation","謹慎評估")}},
        "行政負擔":{"select":{"name":score.get("admin_burden","中")}},
        "狀態":{"select":{"name":"待評估"}},
        "AI分析摘要":{"rich_text":[{"text":{"content":score.get("summary","")[:500]}}]},
        "風險提醒":{"rich_text":[{"text":{"content":"、".join(score.get("risks",[]))[:500]}}]},
        "來源":{"select":{"name":"爬蟲自動"}},
    }
    if tender.get("link"): props["原始連結"]={"url":tender["link"]}
    if budget_num: props["預算"]={"number":budget_num}
    try:
        res = requests.post("https://api.notion.com/v1/pages",
            headers={"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"},
            json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props},timeout=15)
        return res.status_code == 200
    except: return False


async def main():
    print(f"LUNVIA 標案爬蟲啟動 — {TODAY}")
    tenders = await scrape_all()
    if not tenders:
        print("今日無新標案")
        return
    saved = skipped = 0
    for i, tender in enumerate(tenders, 1):
        print(f"[{i}/{len(tenders)}] {tender['name'][:40]}")
        score = evaluate_tender(tender)
        if not score: skipped += 1; continue
        print(f"  {score['overall_score']}/10 -> {score['recommendation']}")
        if score['overall_score'] < MIN_SCORE: skipped += 1; continue
        if save_to_notion(tender, score):
            saved += 1
        else: skipped += 1
        time.sleep(0.5)
    print(f"完成！存入{saved}筆，略過{skipped}筆")

if __name__ == "__main__":
    asyncio.run(main())
