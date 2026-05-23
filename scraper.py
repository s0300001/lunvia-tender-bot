"""診斷：把 HTML 回傳寫進 debug.txt 並 commit 回 repo"""
import os, requests, base64, json
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "s0300001/lunvia-tender-bot"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
})

# GET first
r1 = SESSION.get(SEARCH_URL, timeout=15)
print(f"GET: {r1.status_code}, cookies: {dict(r1.cookies)}")

# POST
r2 = SESSION.post(SEARCH_URL, data={
    "Keyword": "設計",
    "OrderBy": "1",
    "Submit": "查詢",
}, timeout=20)
print(f"POST: {r2.status_code}, url: {r2.url}")

# decode
try:
    content = r2.content.decode("big5", errors="replace")
except:
    content = r2.text

# extract key info
soup = BeautifulSoup(content, "html.parser")
rows = soup.find_all("tr")

debug = []
debug.append(f"GET status: {r1.status_code}")
debug.append(f"POST status: {r2.status_code}")
debug.append(f"POST url: {r2.url}")
debug.append(f"Total <tr>: {len(rows)}")
debug.append("--- First 500 chars of HTML ---")
debug.append(content[:500])
debug.append("--- All <tr> with <td> ---")
for i, row in enumerate(rows[:30]):
    cells = row.find_all("td")
    if cells:
        texts = [c.get_text(strip=True)[:50] for c in cells[:5]]
        debug.append(f"Row {i}: {' | '.join(texts)}")
debug.append("--- All <input> ---")
for inp in soup.find_all("input")[:20]:
    debug.append(f"input: name={inp.get('name','')} type={inp.get('type','')} value={str(inp.get('value',''))[:30]}")

debug_txt = "\n".join(debug)
print(debug_txt)

# 寫回 GitHub
if GITHUB_TOKEN:
    encoded = base64.b64encode(debug_txt.encode()).decode()
    # check if file exists
    r_check = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/debug.txt",
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )
    sha = r_check.json().get("sha", "") if r_check.status_code == 200 else ""
    
    payload = {"message": "Add debug.txt", "content": encoded}
    if sha:
        payload["sha"] = sha
    
    r_put = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/debug.txt",
        headers={"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=15
    )
    print(f"GitHub write: {r_put.status_code}")
