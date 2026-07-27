import re

def main():
    input_file = r"C:\Users\moral\.gemini\antigravity-ide\scratch\extracted_urls.txt"
    output_file = r"C:\Users\moral\.gemini\antigravity-ide\scratch\filtered_urls.txt"
    
    ignore_patterns = [
        r"schemas\.android\.com",
        r"schemas\.xmlsoap\.org",
        r"w3\.org",
        r"google",
        r"facebook",
        r"unity3d",
        r"github",
        r"android\.com",
        r"crashlytics",
        r"sentry",
        r"firebase",
        r"okhttp",
        r"adjust\.com",
        r"app-measurement",
        r"amplitude\.com",
        r"applovin",
        r"adcolony",
        r"fyber",
        r"vungle",
        r"chartboost",
        r"ironsource",
        r"mintegral",
        r"bidmachine",
        r"wortise",
        r"pangle",
        r"inmobi",
        r"amazon-adsystem",
        r"pubmatic",
        r"criteo",
        r"doubleclick",
        r"adservice",
        r"adnxs",
        r"openx",
        r"rubiconproject",
        r"cas\.ms",
        r"app-ads",
        r"comet/campaign",
        r"adjust_external_click_id",
        r"playsimple",
        r"axlebolt",
        r"tripcross",
        r"crossword"
    ]
    
    ignore_regex = re.compile("|".join(ignore_patterns), re.IGNORECASE)
    
    filtered_entries = []
    
    with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("==="):
                continue
            
            # Check if any ignore pattern matches
            if ignore_regex.search(line):
                continue
                
            filtered_entries.append(line)
            
    print(f"Filtered down to {len(filtered_entries)} entries.")
    with open(output_file, "w", encoding="utf-8") as out:
        for entry in filtered_entries:
            out.write(entry + "\n")

if __name__ == "__main__":
    main()
