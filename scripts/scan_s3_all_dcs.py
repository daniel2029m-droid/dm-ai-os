import socket
import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"
VOLUME_ID = "tbupq29n08"

# Test all official S3 endpoints from RunPod docs
DCS = [
    "us-tx-3", "us-tx-1", "us-tx-2", "us-ca-2", "us-ga-2",
    "us-il-1", "us-ks-2", "us-md-1", "us-mo-1", "us-nc-1",
    "us-nc-2", "us-ne-1", "us-wa-1", "eu-cz-1", "eu-ro-1"
]

print("=== CHECKING ALL RUNPOD S3 ENDPOINTS ===")

for dc in DCS:
    host = f"s3api-{dc}.runpod.io"
    try:
        ip = socket.gethostbyname(host)
        print(f"[RESOLVED] {host} -> {ip}")
        
        ep = f"https://{host}/"
        s3 = boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=dc,
            config=Config(signature_version="s3v4", s3={'addressing_style': 'path'}, connect_timeout=4, read_timeout=4)
        )
        
        buckets = s3.list_buckets()
        b_names = [b['Name'] for b in buckets.get('Buckets', [])]
        print(f"  --> SUCCESS on {dc}! Buckets: {b_names}")
        
        for b in b_names:
            print(f"  Listing bucket '{b}'...")
            res = s3.list_objects_v2(Bucket=b)
            for item in res.get('Contents', []):
                sz_gb = item['Size'] / (1024**3)
                print(f"    FILE: {item['Key']} ({sz_gb:.2f} GB)")
    except Exception as e:
        print(f"[FAIL] {host}: {e}")
