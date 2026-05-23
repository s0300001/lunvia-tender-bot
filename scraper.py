"""
LUNVIA 標案情報自動爬蟲 (Gemini 版)
每天從台灣採購公報網抓取設計相關標案，AI 評分後存入 Notion
"""

import asyncio, json, os, re, time
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import requests
import google.generativeai as genai

KEYWORDS = [
    "視覺設計","品牌識別","品牌設計","視覺識別","CIS","識別系統",
    "包裝設計","包裝規劃","印刷品設計","刊物設計","出版品設計","年報設計",
    "展覽設計","展示設計","展覽規劃","策展","活動視覺","展場設計",
    "形象設計","形象規劃","推廣設計","宣傳設計","圖像設計","插畫",
    "LOGO設計","標誌設計","吉祥物設計","文宣設計","美編",
]

GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
TW    = timezone(timedelta(hours=8))
NOW   = datetime.now(TW)

# 抓最近 3 天（包含週末補抓）
RECENT_DATES = set()
for i in range(3):
    d = NOW - timedelta(days=i)
    RECENT_DATES.add(d.strftime("%Y/%m/%d"))

SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
MIN_SCORE  = 6

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


async def search_keyword(page, keyword):
    try:
        await page.goto(SEARCH_URL, timeout=30000)
        # 用 type="text" 精準定位關鍵字輸入框，避免誤觸 submit 按鈕
        await page.wait_for_selector('input[name="Keyword"][type="text"]', timeout=10000)
        await page.fill('input[name="Keyword"][type="text"]', keyword)
        await page.click('input[type="submit"][value="查詢"]')
        await page.wait_for_load_state("networkidle", timeout=20000)
        rows = await page.query_selector_all("table tr")
        results = []
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 3: continue
            date_text = (await cells[0].inner_text()).strip()
            if not any(d in date_text for d in RECENT_DATES): continue
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
請評估以下標案，只回傳JSON，不要其他文字或markdown：

標案名稱：{tender['name']}
來源單位：{tender['unit']}
預算：{tender['budget']}
連結：{tender['link']}

{{"overall_score":數字1-10,"recommendation":"強烈建議"或"值得考慮"或"謹慎評估"或"不建議","budget_score":數字1-10,"spec_score":數字1-10,"fit_score":數字1-10,"win_score":數字1-10,"admin_burden":"輕"或"中"或"重","tender_type":"視覺設計"或"品牌識別"或"展覽規劃"或"包裝設計"或"空間設計"或"綜合設計","budget_assessment":"合理"或"偏低"或"偏高"或"不明","summary":"30字以內整體摘要","risks":["風險1","風險2"]}}"""
    try:
        res  = model.generate_content(prompt)
        text = re.sub(r"```json|```", "", res.text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"  評分失敗：{e}")
        return None


def save_to_notion(tender, score):
    nums = re.findall(r"\d+", tender.get("budget","").replace(",",""))
    budget_num = int(nums[0]) if nums else None
    props = {
        "標案名稱":  {"title":     [{"text":{"content":tender["name"][:200]}}]},
        "來源單位":  {"rich_text": [{"text":{"content":tender["unit"][:200]}}]},
        "類型":      {"select":    {"name":score.get("tender_type","視覺設計")}},
        "AI綜合評分":{"number":    score.get("overall_score")},
        "預算分數":  {"number":    score.get("budget_score")},
        "規格分數":  {"number":    score.get("spec_score")},
        "適配分數":  {"number":    score.get("fit_score")},
        "勝率分數":  {"number":    score.get("win_score")},
        "預算評估":  {"select":    {"name":score.get("budget_assessment","不明")}},
        "投標建議":  {"select":    {"name":score.get("recommendation","謹慎評估")}},
        "行政負擔":  {"select":    {"name":score.get("admin_burden","中")}},
        "狀態":      {"select":    {"name":"待評估"}},
        "AI分析摘要":{"rich_text": [{"text":{"content":score.get("summary","")[:500]}}]},
        "風險提醒":  {"rich_text": [{"text":{"content":"、".join(score.get("risks",[]))[:500]}}]},
        "來源":      {"select":    {"name":"爬蟲自動"}},
    }
    if tender.get("link"):  props["原始連結"] = {"url": tender["link"]}
    if budget_num:          props["預算"]     = {"number": budget_num}
    try:
        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers={"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"},
            json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props},
            timeout=15)
        return res.status_code == 200
    except:
        return False


async def main():
    dates_str = ', '.join(sorted(RECENT_DATES))
    print(f"LUNVIA 標案爬蟲啟動 — 抓最近3天 ({dates_str})")
    tenders = await scrape_all()
    if not tenders:
        print("最近3天無相關標案"); return
    saved = skipped = 0
    for i, tender in enumerate(tenders, 1):
        print(f"[{i}/{len(tenders)}] {tender['name'][:40]}")
        score = evaluate_tender(tender)
        if not score: skipped += 1; continue
        print(f"  {score['overall_score']}/10 -> {score['recommendation']}")
        if score['overall_score'] < MIN_SCORE: skipped += 1; continue
        if save_to_notion(tender, score): saved += 1
        else: skipped += 1
        time.sleep(0.5)
    print(f"完成！存入{saved}筆，略過{skipped}筆")

if __name__ == "__main__":
    asyncio.run(main())
