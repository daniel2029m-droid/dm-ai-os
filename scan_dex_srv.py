import re

def main():
    dex_path = r"C:\Users\moral\Downloads\chocoTV_extract\contents\classes3.dex"
    try:
        with open(dex_path, "rb") as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading DEX: {e}")
        return
        
    # Search for "appcreator" or "/srv/"
    # We want to find any text strings around these patterns
    patterns = [b"appcreator", b"/srv/"]
    for p in patterns:
        for m in re.finditer(p, data):
            idx = m.start()
            start = max(0, idx - 100)
            end = min(len(data), idx + len(p) + 100)
            chunk = data[start:end]
            printable = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            print(f"Match for {p.decode()} @ {idx}:")
            print(f"  {printable}")

if __name__ == "__main__":
    main()
