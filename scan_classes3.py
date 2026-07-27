import re

def main():
    # Scan classes3.dex specifically for AppCreator24 related URLs and webview paths
    dex_path = r"C:\Users\moral\Downloads\chocoTV_extract\contents\classes3.dex"
    
    with open(dex_path, "rb") as f:
        data = f.read()
    
    # Extract all readable strings >= 8 chars
    pattern = re.compile(rb"[ -~]{8,300}")
    
    results = set()
    
    for m in pattern.finditer(data):
        s = m.group(0)
        s_lower = s.lower()
        
        keywords = [
            b"wv_", b"webview", b"http", b"appcreator", b"idapp",
            b"video", b"player", b"canal", b"tv", b"live", b"stream",
            b"categoria", b"categ", b"section", b"menu", b"list",
            b"php", b"/srv/", b"chocopop", b"choco",
        ]
        
        for kw in keywords:
            if kw in s_lower:
                decoded = s.decode("utf-8", errors="ignore").strip()
                if len(decoded) > 7:
                    results.add(decoded)
                break
    
    print(f"Found {len(results)} strings. Showing relevant ones:\n")
    
    # Filter and categorize
    urls = [r for r in results if r.startswith("http") or r.startswith("/srv")]
    wv_keys = [r for r in results if r.startswith("wv_")]
    php_paths = [r for r in results if ".php" in r]
    other = [r for r in results if r not in urls and r not in wv_keys and r not in php_paths]
    
    print("=== URLs ===")
    for u in sorted(urls):
        print(f"  {u}")
    
    print("\n=== WV Keys ===")
    for w in sorted(wv_keys):
        print(f"  {w}")
        
    print("\n=== PHP Paths ===")
    for p in sorted(php_paths):
        print(f"  {p}")
    
    print(f"\n=== Other ({len(other)}) ===")
    for o in sorted(other)[:50]:
        print(f"  {o}")

if __name__ == "__main__":
    main()
