"""
Fast RunPod S3 Endpoint Finder
"""
import httpx
import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"

CANDIDATES = [
    "https://s3.runpod.io",
    "https://s3-us-tx-3.runpod.io",
    "https://storage.runpod.io",
    "https://s3.us-tx-3.runpod.net",
    "https://s3-us-tx-3.runpod.net",
    "https://us-tx-3.storage.runpod.io",
]

def test_endpoints():
    print("Testing RunPod S3 candidate endpoints...")
    valid_endpoint = None
    for ep in CANDIDATES:
        try:
            r = httpx.get(ep, timeout=2.0)
            print(f"[HTTP {r.status_code}] {ep}")
            if r.status_code in (200, 403, 400):
                valid_endpoint = ep
                break
        except Exception as e:
            print(f"[FAIL] {ep}: {e}")

    if not valid_endpoint:
        print("Testing with boto3 signature directly on s3.runpod.io...")
        valid_endpoint = "https://s3.runpod.io"

    print(f"\nAttempting S3 Client operations on: {valid_endpoint}")
    for reg in ['us-tx-3', 'us-east-1', 'us-west-1']:
        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=ACCESS_KEY,
                aws_secret_access_key=SECRET_KEY,
                endpoint_url=valid_endpoint,
                config=Config(signature_version='s3v4', connect_timeout=3, read_timeout=3),
                region_name=reg
            )
            res = s3.list_buckets()
            print(f"SUCCESS on region '{reg}'! Buckets: {res.get('Buckets')}")
            for b in res.get('Buckets', []):
                b_name = b['Name']
                print(f"Listing bucket '{b_name}'...")
                objs = s3.list_objects_v2(Bucket=b_name)
                for item in objs.get('Contents', []):
                    size_gb = item['Size'] / (1024**3)
                    print(f"  FILE: {item['Key']} ({size_gb:.2f} GB)")
            return
        except Exception as e:
            print(f"Failed region '{reg}': {e}")

if __name__ == "__main__":
    test_endpoints()
