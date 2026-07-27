import re

def main():
    dex_path = r"C:\Users\moral\Downloads\chocoTV_extract\contents\classes3.dex"
    try:
        with open(dex_path, "rb") as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading DEX: {e}")
        return
        
    matches = re.finditer(b"appcreator24\\.com", data, re.IGNORECASE)
    for m in matches:
        idx = m.start()
        start = max(0, idx - 120)
        end = min(len(data), idx + len(m.group(0)) + 120)
        chunk = data[start:end]
        printable = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        print(f"Index {idx}:")
        print(f"  {printable}")

if __name__ == "__main__":
    main()
