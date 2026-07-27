import requests
import concurrent.futures

urls = [
    ("Telefe HD", "https://telefe-live.stmv.cloud/telefe/telefe/playlist.m3u8"),
    ("TV Pública", "https://livestream-f.akamaihd.net/livestream/smil:rta-hd.smil/playlist.m3u8"),
    ("Canal 13", "https://mdstrm.com/live-stream-playlist/5b0f9f649b7d4a4f15c4b8b5.m3u8"),
    ("América TV", "https://prepublish.f.qaotic.net/a07/americahls-100056/playlist_720p.m3u8"),
    ("TyC Sports", "https://tyc-live.stmv.cloud/tyc/tyc/playlist.m3u8"),
    ("TyC Sports 2", "https://tyc-live.stmv.cloud/tycsports2/tycsports2/playlist.m3u8"),
    ("ESPN Premium", "https://vcp.p9.com.ar/espn/espn.m3u8"),
    ("ESPN 2", "https://vcp.p9.com.ar/espn2/espn2.m3u8"),
    ("ESPN 3", "https://vcp.p9.com.ar/espn3/espn3.m3u8"),
    ("ESPN 4", "https://vcp.p9.com.ar/espn4/espn4.m3u8"),
    ("TN Noticias", "https://tn-live.stmv.cloud/tn/tn/playlist.m3u8"),
    ("A24", "https://g5.vxral-slo.transport.edge-access.net/a12/ngrp:a24-100056_all/playlist.m3u8"),
    ("C5N", "https://mdstrm.com/live-stream-playlist/57f3219d4fb6cf2b00ad3895.m3u8"),
    ("Infobae TV", "https://mdstrm.com/live-stream-playlist/5d4313d0bd6f1b07e2d4e0ae.m3u8"),
    ("IP Noticias", "https://videostream.shockmedia.com.ar/hls/ipnoticias/ipnoticias.m3u8"),
    ("La Nación+", "https://mdstrm.com/live-stream-playlist/5e3f2d6db6b7e90034050b6e.m3u8"),
    ("Canal 26/247", "https://panel.host-live.com:19360/cn247tv/cn247tv.m3u8"),
    ("DirecTV Sports", "https://mdstrm.com/live-stream-playlist/57e0c0af4fb6cf2b00a4f84e.m3u8"),
    ("DirecTV Sports 2", "https://mdstrm.com/live-stream-playlist/57e0c0af4fb6cf2b00a4f84f.m3u8"),
    ("Canal 9", "https://mdstrm.com/live-stream-playlist/5b10097a9b7d4a4f15c4f1f6.m3u8"),
    ("Net TV", "https://videostream.shockmedia.com.ar/hls/nettv/nettv.m3u8"),
    ("Argentinísima", "https://stream1.sersat.com/hls/argentinisima.m3u8"),
    ("Canal 7 Neuquén", "https://stream.arcast.com.ar/c7nq/ngrp:c7nq_all/playlist.m3u8"),
    ("Canal 7 Salta", "https://vivo.solumedia.com:19360/canal7salta/canal7salta.m3u8"),
    ("ABTV Bariloche", "https://videostream.shockmedia.com.ar/hls/abtvbariloche/abtvbariloche.m3u8"),
    ("Canal 2 MdP", "https://tv.streamcasthd.com:3641/live/canal2mdplive.m3u8"),
    ("Aire de Santa Fe", "https://mdstrm.com/live-stream/6931a0eb06778645348008e0.m3u8"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "*/*",
    "Origin": "https://moratv.vercel.app",
    "Referer": "https://moratv.vercel.app/"
}

def check(name, url):
    try:
        r = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
        ok = r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X-" in r.text or len(r.content) > 100)
        return (name, url, r.status_code, ok, r.text[:80].replace("\n","") if ok else "")
    except Exception as e:
        return (name, url, 0, False, str(e)[:60])

print("Testeando streams...\n")
working = []
broken = []

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(check, n, u): (n,u) for n,u in urls}
    for f in concurrent.futures.as_completed(futures):
        name, url, code, ok, content = f.result()
        if ok:
            working.append((name, url))
            print(f"  [OK ] {name}")
        else:
            broken.append((name, url, code))
            print(f"  [FAIL {code}] {name} -- {content[:50]}")

print(f"\n=== RESUMEN ===")
print(f"Funcionan: {len(working)}")
print(f"Rotos: {len(broken)}")
