"""
RunPod S3 Storage Inspector
===========================
Uses RunPod S3 API credentials to list buckets and object keys directly from local PC.
Costs $0 USD GPU credits.
"""
import sys
import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"

# Potential RunPod S3 endpoints
ENDPOINTS = [
    "https://s3.runpod.io",
    "https://s3.us-tx-3.runpod.io",
    "https://storage.runpod.io",
    "https://us-tx-3.storage.runpod.io",
    "https://s3.us-east-1.runpod.io",
    "https://s3.eu-central-1.runpod.io",
]

def check_s3():
    print("=== TESTING RUNPOD S3 STORAGE ACCESS ===")
    
    for endpoint in ENDPOINTS:
        print(f"\nTesting endpoint: {endpoint}")
        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=ACCESS_KEY,
                aws_secret_access_key=SECRET_KEY,
                endpoint_url=endpoint,
                config=Config(signature_version='s3v4', connect_timeout=4, read_timeout=4),
                region_name='us-tx-3'
            )
            
            # List buckets
            response = s3.list_buckets()
            buckets = [b['Name'] for b in response.get('Buckets', [])]
            print(f"[OK] CONNECTED! Buckets found ({len(buckets)}): {buckets}")
            
            for bucket in buckets:
                print(f"\n--- Objects in bucket: '{bucket}' ---")
                paginator = s3.get_paginator('list_objects_v2')
                count = 0
                total_size = 0
                for page in paginator.paginate(Bucket=bucket):
                    for obj in page.get('Contents', []):
                        count += 1
                        size_mb = obj['Size'] / (1024 * 1024)
                        size_gb = obj['Size'] / (1024 * 1024 * 1024)
                        total_size += obj['Size']
                        if size_gb >= 0.1:
                            print(f"  FILE: {obj['Key']} ({size_gb:.2f} GB)")
                        else:
                            print(f"  FILE: {obj['Key']} ({size_mb:.1f} MB)")
                print(f"Total objects in {bucket}: {count} | Total Size: {total_size / (1024**3):.2f} GB")
            return
        except Exception as e:
            print(f"[FAIL] Could not list on {endpoint}: {e}")

if __name__ == "__main__":
    check_s3()
