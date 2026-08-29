import socket
import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"

DOMAINS = [
    "s3.us-tx-3.runpod.net",
    "us-tx-3.s3.runpod.net",
    "s3-us-tx-3.runpod.net",
    "storage.runpod.io",
    "s3.runpod.io",
    "s3.runpod.net",
    "s3.us-tx-3.runpod.io",
    "network-volume.runpod.io",
    "nv.runpod.io",
    "us-tx-3.nv.runpod.io",
]

print("=== CHECKING RUNPOD S3 DOMAIN RESOLUTION ===")
resolved = []

for d in DOMAINS:
    try:
        ip = socket.gethostbyname(d)
        print(f"[RESOLVED] {d} -> {ip}")
        resolved.append(f"https://{d}")
    except Exception:
        print(f"[FAIL] {d}")

for ep in resolved:
    print(f"\nTesting S3 API with credentials on: {ep}")
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            endpoint_url=ep,
            config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=5),
            region_name='us-tx-3'
        )
        res = s3.list_buckets()
        print(f"SUCCESS on {ep}! Buckets: {res.get('Buckets')}")
        for b in res.get('Buckets', []):
            bname = b['Name']
            print(f"\nBucket: {bname}")
            objs = s3.list_objects_v2(Bucket=bname)
            for item in objs.get('Contents', []):
                print(f"  FILE: {item['Key']} ({item['Size'] / (1024**3):.2f} GB)")
    except Exception as e:
        print(f"S3 API query error on {ep}: {e}")
