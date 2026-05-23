"""DEBUG v4 - 把 HTML 結果寫入 Notion"""
import os, requests
from bs4 import BeautifulSoup

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": SEARCH_URL,
})

SESSION.get(SEARCH_URL, timeout=15)
resp = SESSION.post(SEARCH_URL, data={
    "Keyword": "設計",
    "OrderBy": "1",
    "Submit": "查詢",
}, timeout=20)

try:
    content = resp.content.decode("big5", errors="replace")
except:
    content = resp.text

soup = BeautifulSoup(content, "html.parser")
rows = soup.find_all("tr")

# 取前20筆 row 的資料
debug_lines = [
    f"Status: {resp.status_code}",
    f"URL: {resp.url}",
    f"Total rows: {len(rows)}",
    "---",
]
for i, row in enumerate(rows[:20]):
    cells = row.find_all("td")
    if cells:
        texts = " | ".join(c.get_text(strip=True)[:40] for c in cells[:4])
        debug_lines.append(f"Row {i}: {texts}")

debug_text = "\n".join(debug_lines)
print(debug_text)

# 寫入 Notion
requests.post(
    "https://api.notion.com/v1/pages",
    headers={"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
    json={
        "parent": {"database_id": "fc1449a1-eb17-4e36-8215-b83de29d3a57"},
        "properties": {
            "品牌名稱": {"title": [{"text": {"content": "DEBUG 爬蟲結果"}}]},
            "視覺問題": {"rich_text": [{"text": {"content": debug_text[:2000]}}]},
        }
    },
    timeout=10
)
print("Written to Notion Lead Database")
