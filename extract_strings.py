import re
import os

def main():
    root_dir = r"C:\Users\moral\Downloads\chocoTV_extract\contents"
    
    # Extract all readable strings from dex files (length 6-200)
    # Focus on strings that look like channel names or URLs
    strings_found = set()
    
    # Pattern for extractable ASCII strings >= 6 chars
    pattern = re.compile(rb"[ -~]{6,200}")
    
    keywords = [
        b"canal", b"channel", b"choco", b"vivo", b"live", b"stream",
        b"video", b"play", b"m3u", b"rtmp", b"hls", b".ts", b"token",
        b"tv", b"telev", b"senal", b"cadena",
    ]
    
    results = []
    
    for file in sorted(os.listdir(root_dir)):
        if file.endswith(".dex"):
            fpath = os.path.join(root_dir, file)
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                for m in pattern.finditer(data):
                    s = m.group(0)
                    s_lower = s.lower()
                    for kw in keywords:
                        if kw in s_lower:
                            decoded = s.decode("utf-8", errors="ignore").strip()
                            # Filter noise
                            if len(decoded) > 5 and decoded not in strings_found:
                                # Skip known SDK strings
                                skip = ["google", "facebook", "admob", "chartboost", "pangle", 
                                       "vungle", "startapp", "inmobi", "unity", "appnext",
                                       "firebase", "sdk", "android", "import", "package",
                                       "com.chart", "com.google", "com.face", "com.unity"]
                                if not any(sk in decoded.lower() for sk in skip):
                                    strings_found.add(decoded)
                                    results.append(f"[{file}] {decoded}")
                            break
            except Exception as e:
                print(f"Error reading {file}: {e}")
    
    print(f"\nFound {len(results)} relevant strings:\n")
    for r in sorted(set(results)):
        print(f"  {r}")

if __name__ == "__main__":
    main()
