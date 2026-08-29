"""
RunPod S3 Storage Inspector (Official Endpoint)
==============================================
Direct inspection of Network Volume tbupq29n08 in US-TX-3.
Costs $0 USD GPU credits.
"""
import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"
VOLUME_ID = "tbupq29n08"
DATACENTER = "us-tx-3"
ENDPOINT = f"https://s3api-{DATACENTER}.runpod.io/"

def inspect_network_volume():
    print(f"=== INSPECTING RUNPOD S3 VOLUME '{VOLUME_ID}' ({DATACENTER}) ===")
    print(f"Endpoint URL: {ENDPOINT}")

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=DATACENTER,
        config=Config(signature_version="s3v4", connect_timeout=8, read_timeout=8)
    )

    try:
        # Check buckets
        buckets_resp = s3.list_buckets()
        bucket_names = [b["Name"] for b in buckets_resp.get("Buckets", [])]
        print(f"[OK] Buckets available on your account: {bucket_names}")

        target_bucket = VOLUME_ID if VOLUME_ID in bucket_names else (bucket_names[0] if bucket_names else VOLUME_ID)
        print(f"\nListing contents of bucket/volume: '{target_bucket}'...")

        paginator = s3.get_paginator("list_objects_v2")
        total_files = 0
        total_size_bytes = 0

        for page in paginator.paginate(Bucket=target_bucket):
            contents = page.get("Contents", [])
            for item in contents:
                total_files += 1
                sz = item["Size"]
                total_size_bytes += sz
                size_mb = sz / (1024 * 1024)
                size_gb = sz / (1024 * 1024 * 1024)
                if size_gb >= 0.1:
                    print(f"  FILE: {item['Key']} -> {size_gb:.2f} GB ({sz:,} bytes)")
                else:
                    print(f"  FILE: {item['Key']} -> {size_mb:.2f} MB ({sz:,} bytes)")

        print("-" * 60)
        print(f"TOTAL FILES FOUND: {total_files}")
        print(f"TOTAL VOLUME SIZE: {total_size_bytes / (1024**3):.2f} GB ({total_size_bytes:,} bytes)")
        print("=" * 60)

    except Exception as e:
        print(f"[ERROR] S3 inspection error: {e}")

if __name__ == "__main__":
    inspect_network_volume()
