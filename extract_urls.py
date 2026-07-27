import os
import re

def extract_strings(file_path):
    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []
    
    # Simple regex to find ASCII strings of length 4 or more
    ascii_strings = re.findall(b"[\\x20-\\x7E]{4,}", data)
    
    urls = []
    m3u_lines = []
    
    # Pattern for URLs
    url_pattern = re.compile(r"https?://[a-zA-Z0-9.\-_/]+(?:\.m3u8?|\.ts|\.mp4|\.mkv|\?|[a-zA-Z0-9.\-_/]+)*")
    
    for s in ascii_strings:
        try:
            s_str = s.decode("utf-8", errors="ignore")
            # If it looks like a URL
            if "http://" in s_str or "https://" in s_str:
                urls.append(s_str)
            # If it mentions m3u or m3u8
            if "m3u" in s_str.lower() or "m3u8" in s_str.lower():
                m3u_lines.append(s_str)
        except Exception:
            pass
            
    return urls, m3u_lines

def main():
    root_dir = r"C:\Users\moral\Downloads\chocoTV_extract\contents"
    all_urls = set()
    all_m3u_info = set()
    
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            file_path = os.path.join(root, file)
            # Scan files (especially .dex, .xml, .js, .json)
            if file.endswith((".dex", ".xml", ".js", ".json", ".properties", ".txt", ".bin")):
                urls, m3u_lines = extract_strings(file_path)
                for u in urls:
                    all_urls.add((file, u))
                for m in m3u_lines:
                    all_m3u_info.add((file, m))
                    
    print(f"Found {len(all_urls)} URLs:")
    with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\extracted_urls.txt", "w", encoding="utf-8") as out:
        out.write("=== URLS ===\n")
        for file, url in sorted(all_urls):
            out.write(f"[{file}] {url}\n")
            
        out.write("\n=== M3U/M3U8 REFERENCES ===\n")
        for file, m3u in sorted(all_m3u_info):
            out.write(f"[{file}] {m3u}\n")

if __name__ == "__main__":
    main()
