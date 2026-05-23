"""
LUNVIA 標案情報自動爬蟲 v6
核心修正：改用 searchbytitle（按關鍵字搜尋），不再依賴日期
原本 searchbriefbydate 在週末/假日會回傳 0，這是根本問題
"""
import json, os, re, time, requests
from datetime import datetime, timezone, timedelta
import google.generativeai as genai

KEYWORDS = [
    "視覺設計", "品牌識別", "品牌設計",
    "包裝設計", "印刷品設計",
    "展覽設計", "展示設計", "展覽規劃",
    "形象設計", "推廣設計", "宣傳設計",
    "LOGO設計", "標誌設計", "吉祥物設計",
]

GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

TW  = timezone(timedelta(hours=8))
NOW = datetime.now(TW)

# 抓最近 14 天（涵蓋兩週平日，避免週末問題）
CUTOFF = NOW - timedelta(days=14)

# v6：改用 searchbytitle，不用 searchbriefbydate
API_SEARCH = "https://pcc.g0v.ronny.tw/api/searchbytitle"
MIN_SCORE  = 3

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── 工具函數 ────────────────────────────────────────────

def fetch_by_keyword(keyword, max_pages=3):
    """用關鍵字搜尋標案，最多抓 max_pages 頁"""
    results = []
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(
                API_SEARCH,
                params={"query": keyword, "page": page},
                timeout=15
            )
            if r.status_code != 200:
                break
            data = r.json()
            records = data.get("records", [])
            if not records:
                break
            results.extend(records)
            if len(records) < 10:
                break
        except Exception as e:
            print(f"  [錯誤] {keyword} p{page}: {e}")
            break
        time.sleep(0.3)
    return results


def parse_date(record):
    """解析標案日期，回傳 datetime 或 None"""
    for field in ["date", "brief_date", "publish_date"]:
        raw = record.get(field, "")
        if not raw:
            continue
        raw = str(raw).strip()
        try:
            if "/" in raw:
                dt = datetime.strptime(raw[:10], "%Y/%m/%d")
            elif len(raw) >= 8:
                dt = datetime.strptime(raw[:8], "%Y%m%d")
            else:
                continue
            return dt.replace(tzinfo=TW)
        except ValueError:
            continue
    return None


def is_recent(record):
    """判斷標案是否在最近 14 天內"""
    dt = parse_date(record)
    if dt is None:
        return True
    return dt >= CUTOFF


def score_with_gemini(record):
    """用 Gemini 分析標案，回傳分析結果 dict"""
    name   = record.get("brief_name", record.get("title", "未知"))
    budget = record.get("budget", "不明")
    unit   = record.get("unit_name", record.get("機關名稱", "不明"))
    detail = record.get("brief", record.get("description", ""))[:500]

    prompt = f"""你是一位台灣設計工作室的業務顧問，專長是品牌識別、視覺設計、展覽視覺、包裝設計。
請評估這個政府標案是否適合投標：

標案名稱：{name}
機關：{unit}
預算：{budget}
說明：{detail}

請回傳 JSON，格式如下（只回傳 JSON，不要其他文字）：
{{
  "ai_summary": "2-3句摘要，說明此標案的核心需求",
  "overall_score": 整數1-10,
  "spec_score": 整數1-10,
  "fit_score": 整數1-10,
  "budget_score": 整數1-10,
  "win_score": 整數1-10,
  "bid_advice": "強烈建議" 或 "值得考慮" 或 "謹慎評估" 或 "不建議",
  "budget_eval": "合理" 或 "偏低" 或 "偏高" 或 "不明",
  "admin_burden": "輕" 或 "中" 或 "重",
  "risk_note": "主要風險（一句話）",
  "services": ["Logo", "VI系統", "包裝設計", "展覽視覺", "空間識別"] 中適用的項目
}}"""

    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as e:
        print(f"  [Gemini 錯誤] {e}")
        return None


def write_to_notion(record, analysis):
    """寫入 Notion 標案情報資料庫"""
    name    = record.get("brief_name", record.get("title", "未知標案"))
    unit    = record.get("unit_name", record.get("機關名稱", ""))
    url     = record.get("url", "")
    budget  = record.get("budget", None)

    dt = parse_date(record)
    date_str = dt.strftime("%Y-%m-%d") if dt else None

    budget_num = None
    if budget:
        nums = re.findall(r"[\d,]+", str(budget))
        if nums:
            try:
                budget_num = float(nums[0].replace(",", ""))
            except ValueError:
                pass

    properties = {
        "標案名稱": {"title": [{"text": {"content": name[:200]}}]},
        "AI分析摘要": {"rich_text": [{"text": {"content": analysis.get("ai_summary", "")[:2000]}}]},
        "AI綜合評分": {"number": analysis.get("overall_score")},
        "規格分數":   {"number": analysis.get("spec_score")},
        "適配分數":   {"number": analysis.get("fit_score")},
        "預算分數":   {"number": analysis.get("budget_score")},
        "勝率分數":   {"number": analysis.get("win_score")},
        "來源單位":   {"rich_text": [{"text": {"content": unit[:200]}}]},
        "風險提醒":   {"rich_text": [{"text": {"content": analysis.get("risk_note", "")[:500]}}]},
        "狀態":       {"select": {"name": "待評估"}},
    }

    if analysis.get("bid_advice"):
        properties["投標建議"] = {"select": {"name": analysis["bid_advice"]}}
    if analysis.get("budget_eval"):
        properties["預算評估"] = {"select": {"name": analysis["budget_eval"]}}
    if analysis.get("admin_burden"):
        properties["行政負擔"] = {"select": {"name": analysis["admin_burden"]}}
    if url:
        properties["原始連結"] = {"url": url}
    if budget_num is not None:
        properties["預算"] = {"number": budget_num}
    if date_str:
        properties["發布日期"] = {"date": {"start": date_str}}

    services = analysis.get("services", [])
    if services:
        properties["適合服務"] = {"multi_select": [{"name": s} for s in services if s]}

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=15)
    if r.status_code == 200:
        print(f"  ✅ 寫入 Notion：{name[:40]}")
    else:
        print(f"  ❌ Notion 失敗 {r.status_code}：{r.text[:200]}")
    return r.status_code == 200


def main():
    print(f"LUNVIA 標案爬蟲 v6 — 搜尋最近 14 天 (cutoff: {CUTOFF.strftime('%Y-%m-%d')})")
    print(f"使用 searchbytitle API\n")

    seen = set()
    candidates = []

    for kw in KEYWORDS:
        records = fetch_by_keyword(kw, max_pages=3)
        recent  = [r for r in records if is_recent(r)]
        new_ones = []
        for r in recent:
            name = r.get("brief_name", r.get("title", ""))
            if name and name not in seen:
                seen.add(name)
                new_ones.append(r)
        candidates.extend(new_ones)
        print(f"[{kw}] 搜尋 {len(records)} 筆 → 近14天 {len(recent)} 筆 → 新增 {len(new_ones)} 筆")

    print(f"\n共 {len(candidates)} 筆候選，開始 Gemini 評分...\n")

    if not candidates:
        print("❌ 沒有候選標案，請確認 API 或擴大關鍵字")
        return

    written = 0
    skipped = 0

    for i, record in enumerate(candidates, 1):
        name = record.get("brief_name", record.get("title", "未知"))
        print(f"[{i}/{len(candidates)}] 評分：{name[:50]}")
        analysis = score_with_gemini(record)
        if analysis is None:
            skipped += 1
            continue
        score = analysis.get("overall_score", 0)
        print(f"  → {score}/10，{analysis.get('bid_advice','?')}")
        if score < MIN_SCORE:
            skipped += 1
            continue
        if write_to_notion(record, analysis):
            written += 1
        time.sleep(1)

    print(f"\n完成！寫入 {written} 筆，跳過 {skipped} 筆")


if __name__ == "__main__":
    main()
