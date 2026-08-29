import boto3
from botocore.config import Config

ACCESS_KEY = "user_31kTM8Iwegz94nuTTbpTepNLJAk"
SECRET_KEY = "rps_I4RJJUS3EV7R7FGSHVN7EL7IFZ0I4U3NVSU415101x42lr"
VOLUME_ID = "tbupq29n08"

# Active endpoints from scan
RESOLVED_DCS = [
    "us-ks-2", "us-ca-2", "us-ga-2", "us-il-1", "us-md-1",
    "us-mo-1", "us-nc-1", "us-nc-2", "us-ne-1", "us-wa-1",
    "eu-cz-1", "eu-ro-1"
]

print(f"=== CHECKING VOLUME '{VOLUME_ID}' ACROSS S3 ENDPOINTS ===")

for dc in RESOLVED_DCS:
    ep = f"https://s3api-{dc}.runpod.io/"
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=dc,
            config=Config(signature_version="s3v4", s3={'addressing_style': 'path'}, connect_timeout=3, read_timeout=3)
        )
        
        # Try listing bucket tbupq29n08 directly
        res = s3.list_objects_v2(Bucket=VOLUME_ID)
        contents = res.get('Contents', [])
        print(f"🎉 FOUND VOLUME ON '{dc}'! Objects count: {len(contents)}")
        for item in contents:
            sz_gb = item['Size'] / (1024**3)
            sz_mb = item['Size'] / (1024**2)
            if sz_gb >= 0.1:
                print(f"   📄 {item['Key']} ({sz_gb:.2f} GB)")
            else:
                print(f"   📄 {item['Key']} ({sz_mb:.1f} MB)")
        break
    except Exception as e:
        err = str(e)
        if "NoSuchBucket" in err or "404" in err or "AccessDenied" in err:
            pass
        else:
            print(f"  [{dc}] {err[:80]}")
