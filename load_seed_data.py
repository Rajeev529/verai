import requests
import json
from pathlib import Path

BASE_URL = "https://verai-production-66d2.up.railway.app"
SEED_DIR = Path(__file__).parent / "seed_data"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def push(scope, context_id, payload, version=1):
    r = requests.post(f"{BASE_URL}/v1/context", json={
        "scope": scope,
        "context_id": context_id,
        "version": version,
        "payload": payload
    })
    print(f"  {scope}: {context_id} → {r.status_code}")

def main():
    # Categories
    for f in (SEED_DIR / "categories").glob("*.json"):
        data = load_json(f)
        push("category", data["slug"], data)

    # Merchants
    for m in load_json(SEED_DIR / "merchants_seed.json")["merchants"]:
        push("merchant", m["merchant_id"], m)

    # Customers
    for c in load_json(SEED_DIR / "customers_seed.json")["customers"]:
        push("customer", c["customer_id"], c)

    # Triggers
    for t in load_json(SEED_DIR / "triggers_seed.json")["triggers"]:
        push("trigger", t["id"], t)

    print("Done!")

if __name__ == "__main__":
    main()