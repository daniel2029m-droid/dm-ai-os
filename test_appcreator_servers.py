import requests

def test_url(url, data=None):
    try:
        if data:
            r = requests.post(url, data=data, timeout=5)
        else:
            r = requests.get(url, timeout=5)
        print(f"URL: {url}")
        print(f"Status: {r.status_code}")
        print(f"Content: {r.text[:500]}")
        print("-" * 50)
        return r.status_code == 200 and len(r.text) > 0, r.text
    except Exception as e:
        # print(f"URL {url} failed: {e}")
        return False, str(e)

def main():
    app_id = "3983634"
    
    # Try different domains
    domains = [
        "www.appcreator24.com",
        "srv1.appcreator24.com",
        "srv2.appcreator24.com",
        "srv3.appcreator24.com",
        "srv4.appcreator24.com",
        "srv5.appcreator24.com",
        "srv6.appcreator24.com",
        "srv7.appcreator24.com",
        "srv8.appcreator24.com",
        "srv9.appcreator24.com",
        "srv10.appcreator24.com"
    ]
    
    # Endpoints
    # 1. get_app.php
    print("Testing get_app.php...")
    for dom in domains:
        url = f"https://{dom}/srv/get_app.php?id={app_id}"
        success, res = test_url(url)
        if success and "html" not in res.lower() and len(res) > 20:
            print(f"🌟 SUCCESS get_app on {dom}!")
            with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\get_app_response.txt", "w", encoding="utf-8") as f:
                f.write(res)
                
    # 2. obtener_buscvideos.php
    print("Testing obtener_buscvideos.php...")
    for dom in domains:
        url = f"https://{dom}/srv/obtener_buscvideos.php?idapp={app_id}"
        success, res = test_url(url)
        if success and len(res) > 5:
            print(f"🌟 SUCCESS obtener_buscvideos on {dom}!")
            with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\videos_response.txt", "w", encoding="utf-8") as f:
                f.write(res)

if __name__ == "__main__":
    main()
