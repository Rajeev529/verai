"""
Run this once after migrate to pre-load all seed data into DB.
Usage: python load_seed_data.py
Place this file in the vera_bot/ root (next to manage.py).
"""
import os, sys, json, django
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
sys.path.insert(0, str(Path(__file__).parent))
django.setup()

from app.models import ContextStore

SEED_DIR = Path(__file__).parent / "seed_data"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def upsert(scope, context_id, payload, version=1):
    ContextStore.objects.update_or_create(
        context_id=context_id,
        defaults={"scope": scope, "version": version, "payload": payload}
    )

def main():
    count = 0

    # ── Categories ──────────────────────────────────────────────────
    cat_dir = SEED_DIR / "categories"
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            data = load_json(f)
            slug = data.get("slug", f.stem)
            upsert("category", slug, data)
            count += 1
            print(f"  category: {slug}")

    # ── Merchants ────────────────────────────────────────────────────
    m_file = SEED_DIR / "merchants_seed.json"
    if m_file.exists():
        for m in load_json(m_file)["merchants"]:
            upsert("merchant", m["merchant_id"], m)
            count += 1
            print(f"  merchant: {m['merchant_id']}")

    # ── Customers ────────────────────────────────────────────────────
    c_file = SEED_DIR / "customers_seed.json"
    if c_file.exists():
        for c in load_json(c_file)["customers"]:
            upsert("customer", c["customer_id"], c)
            count += 1

    # ── Triggers ─────────────────────────────────────────────────────
    t_file = SEED_DIR / "triggers_seed.json"
    if t_file.exists():
        for t in load_json(t_file)["triggers"]:
            upsert("trigger", t["id"], t)
            count += 1

    print(f"\nDone — {count} records loaded.")

if __name__ == "__main__":
    main()
