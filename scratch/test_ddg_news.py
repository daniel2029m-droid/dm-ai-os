import httpx
import re
import urllib.parse

sq = 'inteligencia artificial noticias recientes lanzamientos'
r = httpx.post(
    'https://html.duckduckgo.com/html/',
    data={'q': sq},
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)
raw = r.text

titles = re.findall(
    r'class=["\']result__title["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    raw, re.DOTALL | re.IGNORECASE
)
snippets = re.findall(
    r'class=["\']result__snippet["\'][^>]*>(.*?)</a>',
    raw, re.DOTALL | re.IGNORECASE
)

print('=== TITLES ===')
for t in titles[:5]:
    print('-', re.sub(r'<[^>]+>', '', t[1]).strip())

print('\n=== SNIPPETS ===')
for s in snippets[:5]:
    print('*', re.sub(r'<[^>]+>', '', s).strip())
