import httpx

url = "https://m.media-amazon.com/images/I/41EQ76x852L._SL1500_.jpg"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.amazon.in/",
    "Accept": "image/*",
}

try:
    r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type')}")
    print(f"Size: {len(r.content)} bytes")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")