# Vera Bot — magicpin AI Challenge Submission

## Live URL
```
https://verai-production-66d2.up.railway.app
```

## Endpoints

| Method | URL | Purpose |
|--------|-----|---------|
| GET | /v1/healthz | Liveness check |
| GET | /v1/metadata | Team info + model |
| POST | /v1/context | Store merchant/category/trigger/customer data |
| POST | /v1/tick | Generate smart messages for merchants |
| POST | /v1/reply | Handle merchant reply |

---

## Approach

A **4-layer structured prompt composer** — no vector DB needed since all data is already structured JSON.

```
Judge → POST /v1/context (merchant + category + trigger + customer)
      → POST /v1/tick
           → pick_best_trigger() — urgency-ranked trigger selection
           → compose_message()   — 4 layers injected into LLM prompt
           → OpenRouter (claude-3-haiku) → JSON response
      → returns: body (≤320 chars) + cta + suppression_key + rationale
```

### 4 Context Layers
1. **Merchant** — name, locality, CTR, offers, signals, subscription
2. **Category** — tone, peer stats, digest insight
3. **Trigger** — kind, urgency, payload details
4. **Customer** — state, last visit, services (optional)

### Key Design Decisions
- **Trigger selection**: urgency-ranked, merchant-id matched
- **Message quality**: real numbers only, merchant's own city/locality, single idea per message, suggestive tone
- **Reply handling**: positive / negative / hostile / auto-reply timeout (end after turn 3)
- **Idempotent context**: same version re-push is ignored

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Framework | Django + Django REST Framework |
| LLM | OpenRouter → claude-3-haiku |
| LangChain | PromptTemplate + JsonOutputParser |
| DB | SQLite (Railway persistent volume) |
| Deploy | Railway (gunicorn) |

---

## Setup (Local)

```bash
# 1. Clone + venv
git clone <repo>
cd verai
python -m venv myvenv
myvenv\Scripts\activate  # Windows
pip install -r requirements.txt

# 2. Environment
cp .env.example .env
# Add: OPENROUTER_API_KEY, SECRET_KEY

# 3. DB
python manage.py migrate

# 4. Seed data
python load_seed_data.py

# 5. Run
python manage.py runserver
```

## Environment Variables

```
OPENROUTER_API_KEY=sk-or-xxxxxxxx
SECRET_KEY=your-django-secret-key
DEBUG=False
```

---

## Test

```bash
# Health
curl https://verai-production-66d2.up.railway.app/v1/healthz

# Generate messages
curl -X POST https://verai-production-66d2.up.railway.app/v1/tick \
  -H "Content-Type: application/json" \
  -d '{"available_triggers": ["trg_001_research_digest_dentists", "trg_010_ipl_match_delhi"]}'

```
## Sample Output

```json
{
  "actions": [{
    "merchant_id": "m_001_drmeera_dentist_delhi",
    "trigger_id": "trg_001_research_digest_dentists",
    "body": "Dr. Meera, 190 people in Lajpat Nagar are searching 'Dental Check Up' today. Your ₹299 offer is ready — shall I send it?",
    "cta": "open_ended",
    "suppression_key": "research_digest:m_001_drmeera_dentist_delhi:2026-W18"
  }]
}
```


<!-- tested input on postman -->
POST https://verai-production-66d2.up.railway.app/v1/tick
Content-Type: application/json

{
  "available_triggers": [
    "trg_001_research_digest_dentists",
    "trg_004_perf_dip_bharat",
    "trg_010_ipl_match_delhi",
    "trg_019_chronic_refill_grandfather"
  ]
}
<!-- tested output -->
{
    "actions": [
        {
            "merchant_id": "m_002_bharat_dentist_mumbai",
            "trigger_id": "trg_004_perf_dip_bharat",
            "body": "Bharat, calls at Bharat Dental Care have dropped 50% in the last 7 days. With 220 unique patients this year, would you like to try a targeted offer to boost appointments?",
            "cta": "open_ended",
            "suppression_key": "perf_dip:m_002_bharat_dentist_mumbai:2026-W18"
        },
        {
            "merchant_id": "m_005_pizzajunction_restaurant_delhi",
            "trigger_id": "trg_010_ipl_match_delhi",
            "body": "Hi Suresh, IPL match today at Arun Jaitley Stadium! 2,200 people in Sant Nagar are searching for 'pizza deals' - your 'Buy 1 Get 1 Free' offer could be perfect. Would you like me to promote it to local fans?",
            "cta": "open_ended",
            "suppression_key": "ipl_match_today:m_005_pizzajunction_restaurant_delhi:2026-W17"
        },
        {
            "merchant_id": "m_009_apollo_pharmacy_jaipur",
            "trigger_id": "trg_019_chronic_refill_grandfather",
            "body": "Hi Ramesh, your Apollo Health Plus Pharmacy in Jaipur's Malviya Nagar has 240 chronic patients. With generic metformin SR prices dropping, would you like to audit your shelves and switch eligible diabetic refills to save them ~₹120/month?",
            "cta": "open_ended",
            "suppression_key": "chronic_refill_due:m_009_apollo_pharmacy_jaipur:2026-W18"
        },
        {
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "trigger_id": "trg_001_research_digest_dentists",
            "body": "Dr. Meera, 190 people in Lajpat Nagar are searching 'Dental Check Up' today. Would you like to send your ₹299 offer to capture this demand?",
            "cta": "open_ended",
            "suppression_key": "research:m_001_drmeera_dentist_delhi:2026-W17"
        }
    ]
}
---

