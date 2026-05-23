"""DEBUG v3 - 印出搜尋結果的 HTML 結構"""
import os, time, requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": SEARCH_URL,
})

# 先 GET
resp = SESSION.get(SEARCH_URL, timeout=15)
print(f"GET status: {resp.status_code}, encoding: {resp.encoding}")

# POST 搜尋「視覺設計」
resp = SESSION.post(SEARCH_URL, data={
    "Keyword": "視覺設計",
    "OrderBy": "1",
    "Submit": "查詢",
}, timeout=20)
print(f"POST status: {resp.status_code}")

# 嘗試不同編碼
try:
    content = resp.content.decode("big5", errors="replace")
    print("Decoded as big5")
except:
    content = resp.text
    print(f"Using default encoding: {resp.encoding}")

print(f"Response length: {len(content)}")
print(f"\n=== First 2000 chars ===")
print(content[:2000])

# Parse
soup = BeautifulSoup(content, "html.parser")
rows = soup.find_all("tr")
print(f"\n=== Found {len(rows)} <tr> elements ===")
for i, row in enumerate(rows[:10]):
    cells = row.find_all("td")
    if cells:
        texts = [c.get_text(strip=True)[:30] for c in cells[:4]]
        print(f"Row {i}: {texts}")
