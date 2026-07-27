import os
import re

def main():
    root_dir = r"C:\Users\moral\Downloads\chocoTV_extract\contents"
    hostnames = set()
    
    # regex for hostnames in ASCII data
    pattern = re.compile(b"https?://([a-zA-Z0-9.\\-_]+)")
    
    for file in os.listdir(root_dir):
        if file.endswith(".dex"):
            file_path = os.path.join(root_dir, file)
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                matches = pattern.finditer(data)
                for m in matches:
                    try:
                        hostnames.add(m.group(1).decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error reading {file}: {e}")
                
    print("Unique Hostnames found:")
    for h in sorted(hostnames):
        print(f"  {h}")

if __name__ == "__main__":
    main()
