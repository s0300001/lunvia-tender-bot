"""
LUNVIA 標案情報自動爬蟲 v5
資料來源：pcc.g0v.ronny.tw (g0v 政府採購 JSON API)
完全不需要瀏覽器，直接 GET JSON
"""
import json, os, re, time, requests
from datetime import datetime, timezone, timedelta
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

# 抓最近5天（涵蓋週末）
RECENT_DATES = [(NOW - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]

API_BASE  = "https://pcc.g0v.ronny.tw/api/searchbriefbydate"
MIN_SCORE = 3

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def fetch_tenders_by_keyword(keyword):
    """從 pcc.g0v.ronny.tw 抓特定關鍵字的標案"""
    results = []
    seen = set()
    for date in RECENT_DATES:
        try:
            resp = requests.get(API_BASE, params={
                "date": date,
                "brief": keyword,
            }, timeout=15, headers={"User-Agent": "LUNVIA-TenderBot/1.0"})
            if resp.status_code != 200:
                continue
            data = resp.json()
            records = data.get("records", [])
            for r in records:
                pk = r.get("pk", "")
                if pk in seen:
                    continue
                seen.add(pk)
                name   = r.get("brief", {}).get("title", "").strip()
                unit   = r.get("brief", {}).get("org_name", "").strip()
                budget = str(r.get("brief", {}).get("budget", "")).strip()
                link   = f"https://pcc.g0v.ronny.tw/id/{pk}"
                results.append({
                    "name": name, "unit": unit, "budget": budget,
                    "link": link, "date": date, "keyword": keyword, "pk": pk
                })
        except Exception as e:
            print(f"  [{keyword}/{date}] 錯誤: {e}")
        time.sleep(0.3)
    return results


def scrape_all():
    all_tenders, seen_pks = [], set()
    for kw in KEYWORDS:
        results = fetch_tenders_by_keyword(kw)
        new = 0
        for item in results:
            if item["pk"] not in seen_pks and item["name"]:
                seen_pks.add(item["pk"])
                all_tenders.append(item)
                new += 1
        print(f"  [{kw}] +{new} 筆")
        time.sleep(0.5)
    print(f"共找到 {len(all_tenders)} 筆不重複標案")
    return all_tenders


def evaluate_tender(tender):
    prompt = f"""你是LUNVIA設計工作室負責人，專精品牌視覺、包裝設計、識別設計，單人工作室規模。
請評估以下標案，只回傳JSON，不要其他文字或markdown：
標案名稱：{tender['name']}
來源單位：{tender['unit']}
預算：{tender['budget']}
{{"overall_score":數字1-10,"recommendation":"強烈建議"或"值得考慮"或"謹慎評估"或"不建議","budget_score":數字1-10,"spec_score":數字1-10,"fit_score":數字1-10,"win_score":數字1-10,"admin_burden":"輕"或"中"或"重","tender_type":"視覺設計"或"品牌識別"或"展覽規劃"或"包裝設計"或"空間設計"或"綜合設計","budget_assessment":"合理"或"偏低"或"偏高"或"不明","summary":"30字以內整體摘要","risks":["風險1","風險2"]}}"""
    try:
        res  = model.generate_content(prompt)
        text = re.sub(r"```json|```", "", res.text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"  評分失敗: {e}")
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
            headers={"Authorization":f"Bearer {NOTION_TOKEN}",
                     "Content-Type":"application/json",
                     "Notion-Version":"2022-06-28"},
            json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props},
            timeout=15)
        if res.status_code == 200:
            return True
        print(f"  Notion 錯誤 {res.status_code}: {res.text[:100]}")
        return False
    except Exception as e:
        print(f"  Notion 失敗: {e}")
        return False


def main():
    dates_str = ", ".join(RECENT_DATES[:3])
    print(f"LUNVIA 標案爬蟲 v5 (pcc.g0v.ronny.tw) — {dates_str}")
    tenders = scrape_all()
    if not tenders:
        print("近5天無相關標案"); return
    saved = skipped = 0
    for i, tender in enumerate(tenders, 1):
        print(f"[{i}/{len(tenders)}] {tender['name'][:40]}")
        score = evaluate_tender(tender)
        if not score: skipped += 1; continue
        print(f"  {score['overall_score']}/10 -> {score['recommendation']}")
        if score['overall_score'] < MIN_SCORE: skipped += 1; continue
        if save_to_notion(tender, score):
            print("  ✅ 存入 Notion")
            saved += 1
        else:
            skipped += 1
        time.sleep(0.5)
    print(f"\n完成！存入 {saved} 筆，略過 {skipped} 筆")

if __name__ == "__main__":
    main()
