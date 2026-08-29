import json

data = json.load(open('logs/runpod_discovery_results.json', encoding='utf-8'))

print("=== POPULAR GPU TYPES FOUND IN RUNPOD ===")
for g in data.get('gpu_types', []):
    gid = g.get('id', '')
    if any(k in gid for k in ['4090', '5090', 'L40S', 'A100', '3090', 'A10G', 'L4', 'A40']):
        vram = g.get('memoryInGb')
        sec_price = g.get('securePrice')
        comm_price = g.get('communityPrice')
        sec_spot = g.get('secureSpotPrice')
        print(f"GPU ID: {gid:<25} | Name: {g.get('displayName'):<20} | VRAM: {vram}GB | Secure: ${sec_price}/h | Community: ${comm_price}/h | Spot: ${sec_spot}/h")

print("\n=== USER POD TEMPLATES FOUND ===")
myself = data.get('myself', {})
print(f"User Balance: ${myself.get('clientBalance', 0.0):.2f}")
for t in myself.get('podTemplates', []):
    print(f"Template ID: {t.get('id')} | Name: {t.get('name')} | Image: {t.get('imageName')}")
