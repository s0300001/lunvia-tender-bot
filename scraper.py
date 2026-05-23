"""測試版：不過濾日期，直接把所有結果存 Notion"""
import json, os, re, time, requests
from bs4 import BeautifulSoup
import google.generativeai as genai

GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": SEARCH_URL,
})

def search_keyword(keyword, max_results=3):
    try:
        SESSION.get(SEARCH_URL, timeout=15)
        resp = SESSION.post(SEARCH_URL, data={
            "Keyword": keyword,
            "OrderBy": "1",
            "Submit": "查詢",
        }, timeout=20)

        try:
            content = resp.content.decode("big5", errors="replace")
        except:
            content = resp.text

        soup = BeautifulSoup(content, "html.parser")
        rows = soup.find_all("tr")
        results = []

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            link_el = cells[1].find("a") if len(cells) > 1 else None
            if not link_el:
                continue
            name = link_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue
            date_text = cells[0].get_text(strip=True)
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.taiwanbuying.com.tw/" + href.lstrip("/")
            unit   = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            budget = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            results.append({"name":name,"unit":unit,"budget":budget,"link":href,"date":date_text,"keyword":keyword})
            if len(results) >= max_results:
                break

        total_rows = len(rows)
        print(f"  [{keyword}] total <tr>={total_rows}, 有效結果={len(results)} 筆")
        if results:
            print(f"    第一筆: {results[0]['date']} | {results[0]['name'][:30]}")
        return results
    except Exception as e:
        print(f"  [{keyword}] 錯誤：{e}")
        return []

def save_to_notion(tender, score):
    nums = re.findall(r"\d+", tender.get("budget","").replace(",",""))
    budget_num = int(nums[0]) if nums else None
    props = {
        "標案名稱":  {"title":     [{"text":{"content":tender["name"][:200]}}]},
        "來源單位":  {"rich_text": [{"text":{"content":tender["unit"][:200]}}]},
        "類型":      {"select":    {"name":score.get("tender_type","視覺設計")}},
        "AI綜合評分":{"number":    score.get("overall_score")},
        "投標建議":  {"select":    {"name":score.get("recommendation","謹慎評估")}},
        "狀態":      {"select":    {"name":"待評估"}},
        "AI分析摘要":{"rich_text": [{"text":{"content":score.get("summary","")[:500]}}]},
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
        print(f"  Notion: {res.status_code} {res.text[:80] if res.status_code!=200 else 'OK'}")
        return res.status_code == 200
    except Exception as e:
        print(f"  Notion 錯誤: {e}")
        return False

def evaluate_tender(tender):
    prompt = f"""評估標案，只回傳JSON：
標案名稱：{tender['name']}
來源單位：{tender['unit']}
{{"overall_score":7,"recommendation":"值得考慮","budget_score":6,"spec_score":7,"fit_score":7,"win_score":6,"admin_burden":"中","tender_type":"視覺設計","budget_assessment":"不明","summary":"設計相關標案","risks":["競爭激烈"]}}"""
    try:
        res = model.generate_content(prompt)
        text = re.sub(r"```json|```", "", res.text).strip()
        return json.loads(text)
    except:
        return {"overall_score":7,"recommendation":"值得考慮","budget_score":6,"spec_score":7,"fit_score":7,"win_score":6,"admin_burden":"中","tender_type":"視覺設計","budget_assessment":"不明","summary":"標案待評估","risks":["競爭激烈"]}

def main():
    print("=== 測試版：不過濾日期，只抓前3筆 ===")
    # 只測試前3個關鍵字
    test_keywords = ["視覺設計", "品牌識別", "設計"]
    saved = 0
    seen = set()
    for kw in test_keywords:
        results = search_keyword(kw, max_results=3)
        for r in results:
            if r["name"] not in seen:
                seen.add(r["name"])
                score = evaluate_tender(r)
                if save_to_notion(r, score):
                    saved += 1
        time.sleep(2)
    print(f"完成！共存入 {saved} 筆")

if __name__ == "__main__":
    main()
