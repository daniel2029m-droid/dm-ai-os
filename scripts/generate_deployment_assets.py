import sys
import os
import json
import argparse
from pathlib import Path

try:
    import qrcode
except ImportError:
    print("Error: qrcode module not found. Please install it with 'pip install qrcode[pil]'.")
    sys.exit(1)

def generate_assets(tunnel_url: str):
    deployment_dir = Path("deployment")
    deployment_dir.mkdir(exist_ok=True)
    
    base_api_url = f"{tunnel_url}/v1"
    
    # 1. Generate Web URL QR
    qr_web = qrcode.QRCode(version=1, box_size=10, border=4)
    qr_web.add_data(tunnel_url)
    qr_web.make(fit=True)
    img_web = qr_web.make_image(fill_color="black", back_color="white")
    img_web.save(deployment_dir / "dm_ai_os_qr.png")
    
    # 2. Generate JSON Config
    config = {
        "name": "DM AI OS",
        "base_url": base_api_url,
        "api_key": "dm-secret-key-v1",
        "model": "dm-autonomous-brain"
    }
    json_path = deployment_dir / "openai_connection.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        
    # 3. Generate JSON QR
    qr_json = qrcode.QRCode(version=1, box_size=8, border=4)
    qr_json.add_data(json.dumps(config))
    qr_json.make(fit=True)
    img_json = qr_json.make_image(fill_color="black", back_color="white")
    img_json.save(deployment_dir / "openai_config_qr.png")
    
    print(f"Deployment assets generated successfully in {deployment_dir.absolute()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate DM AI OS Deployment Assets")
    parser.add_argument("--url", required=True, help="Public URL of the tunnel")
    args = parser.parse_args()
    
    # Ensure URL doesn't have trailing slash for consistency
    url = args.url.rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
        
    generate_assets(url)
