import httpx
import re
import urllib.parse

r = httpx.post(
    'https://html.duckduckgo.com/html/',
    data={'q': 'novedades IA esta semana'},
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)
raw_html = r.text

titles = re.findall(
    r'class=["\']result__title["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    raw_html, re.DOTALL | re.IGNORECASE
)

sources = []
for href, title_html in titles[:5]:
    clean_title = re.sub(r'<[^>]+>', '', title_html).strip()
    if 'uddg=' in href:
        m = re.search(r'uddg=([^&]+)', href)
        url = urllib.parse.unquote(m.group(1)) if m else href
    else:
        url = href
    if clean_title:
        sources.append(f"{clean_title}: {url}")

print("Extracted sources:")
for s in sources:
    print("-", s)
