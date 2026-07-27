import os
import re

def search_in_dex(file_path):
    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return
    
    # Search for patterns
    targets = [b"appcreator24", b"get_app", b"chocopop", b"srv"]
    
    print(f"\n--- Scanning {os.path.basename(file_path)} ---")
    for target in targets:
        indices = [m.start() for m in re.finditer(target, data)]
        if indices:
            print(f"Found '{target.decode()}' {len(indices)} times.")
            # Extract surrounding ASCII strings for the first few occurrences
            for idx in indices[:15]:
                start = max(0, idx - 60)
                end = min(len(data), idx + len(target) + 60)
                chunk = data[start:end]
                # Filter printable characters
                printable_chunk = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
                print(f"  @ {idx}: {printable_chunk}")

def main():
    root_dir = r"C:\Users\moral\Downloads\chocoTV_extract\contents"
    for file in os.listdir(root_dir):
        if file.endswith(".dex"):
            search_in_dex(os.path.join(root_dir, file))

if __name__ == "__main__":
    main()
