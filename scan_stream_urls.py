import re
import os

def main():
    root_dir = r"C:\Users\moral\Downloads\chocoTV_extract\contents"
    
    # Patterns for stream URLs
    patterns = [
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}\.m3u8[^\x00\s\"\'<>]*"),
        re.compile(rb"rtmp://[^\x00\s\"\'<>]{5,}"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}/live[^\x00\s\"\'<>]*"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}/stream[^\x00\s\"\'<>]*"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}/hls[^\x00\s\"\'<>]*"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}/playlist[^\x00\s\"\'<>]*"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}/index\.m3u[^\x00\s\"\'<>]*"),
        re.compile(rb"https?://[^\x00\s\"\'<>]{5,}choco[^\x00\s\"\'<>]*"),
    ]
    
    all_found = set()
    
    for file in os.listdir(root_dir):
        if file.endswith(".dex") or file.endswith(".js") or file.endswith(".xml"):
            fpath = os.path.join(root_dir, file)
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                for p in patterns:
                    for m in p.finditer(data):
                        url = m.group(0).decode("utf-8", errors="ignore").strip()
                        # Filter out known ad/sdk URLs
                        skip_keywords = ["google", "facebook", "admob", "chartboost", "pangle", "vungle", "startapp", "inmobi", "unity", "appnext", "firebase", "unityads"]
                        if not any(kw in url.lower() for kw in skip_keywords):
                            all_found.add(url)
            except Exception as e:
                print(f"Error reading {file}: {e}")
    
    # Also scan all assets
    assets_dir = os.path.join(root_dir, "assets")
    if os.path.exists(assets_dir):
        for root, dirs, files in os.walk(assets_dir):
            for file in files:
                fpath = os.path.join(root, file)
                try:
                    with open(fpath, "rb") as f:
                        data = f.read()
                    for p in patterns:
                        for m in p.finditer(data):
                            url = m.group(0).decode("utf-8", errors="ignore").strip()
                            skip_keywords = ["google", "facebook", "admob", "chartboost", "pangle", "vungle", "startapp", "inmobi", "unity", "appnext", "firebase", "unityads"]
                            if not any(kw in url.lower() for kw in skip_keywords):
                                all_found.add(url)
                except Exception as e:
                    pass
    
    print(f"Found {len(all_found)} stream-like URLs:")
    for u in sorted(all_found):
        print(f"  {u}")

if __name__ == "__main__":
    main()
