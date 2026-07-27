with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\extracted_urls.txt", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

keywords = ["tv", "choco", "chotv", "api", "php", "json", "srv", "get", "playlist", "m3u", "channel", "stream", "config"]
ignore_domains = [
    "schemas.android.com", "google", "facebook", "unity3d", "github", "android.com", 
    "crashlytics", "sentry", "firebase", "okhttp", "adjust", "applovin", "vungle", 
    "adcolony", "fyber", "chartboost", "ironsource", "mintegral", "doubleclick"
]

matches = []
for line in lines:
    line = line.strip()
    if not line.startswith("[") or "http" not in line:
        continue
    
    # Check if ignore domains are in line
    if any(domain in line.lower() for domain in ignore_domains):
        continue
        
    # Check if any keyword matches
    if any(kw in line.lower() for kw in keywords):
        matches.append(line)

print(f"Found {len(matches)} matching URLs:")
for m in matches[:50]:
    print(m)

with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\tv_matches.txt", "w", encoding="utf-8") as out:
    for m in matches:
        out.write(m + "\n")
