import requests

def test_endpoint(url, method="GET", data=None):
    try:
        if method == "POST":
            r = requests.post(url, data=data, timeout=8)
        else:
            r = requests.get(url, params=data, timeout=8)
        print(f"[{method}] {url}")
        print(f"  Params/Data: {data}")
        print(f"  Status: {r.status_code}")
        print(f"  Length: {len(r.text)}")
        print(f"  Content: {r.text[:300]}")
        print("-" * 60)
        return r.text
    except Exception as e:
        print(f"[{method}] {url} failed: {e}")
        print("-" * 60)
        return None

def main():
    base_url = "https://www.appcreator24.com"
    app_id = "3983634"
    
    # Try different endpoints
    endpoints = [
        "/srv/acad.php",
        "/srv/buscvideo_visto.php",
        "/srv/obtener_buscvideos.php",
        "/srv/obtener_cards.php",
        "/srv/obtener_gal.php",
        "/srv/obtener_perfil.php",
        "/srv/obtener_profile.php",
        "/srv/obtener_usus.php",
        "/srv/obtenerchats.php",
        "/srv/result.php",
        "/srv/usu_catnotif.php"
    ]
    
    for ep in endpoints:
        url = base_url + ep
        # Test with idapp or idusu
        test_endpoint(url, "GET", {"idapp": app_id, "idusu": "1"})
        test_endpoint(url, "POST", {"idapp": app_id, "idusu": "1"})

if __name__ == "__main__":
    main()
