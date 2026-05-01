import os
import json
import logging

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── LLM + Chain ───────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model="anthropic/claude-3-haiku",
    openai_api_key=os.getenv("OPENROUTER_API_KEY", ""),
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.3,
)
parser = JsonOutputParser()

prompt = PromptTemplate(
    input_variables=["merchant", "category", "trigger", "customer"],
    template="""
You are Vera — magicpin's AI growth assistant for local merchants.
Compose ONE sharp WhatsApp nudge for this merchant.

MERCHANT CONTEXT:
{merchant}

CATEGORY CONTEXT:
{category}

TRIGGER CONTEXT:
{trigger}

CUSTOMER CONTEXT:
{customer}

STRICT RULES:
1. Max 320 characters for body
2. Use ONLY the merchant's own city/locality — never use another city's data
3. Use merchant's EXACT business name from context
4. Use REAL numbers: merchant's own CTR, offer price, customer count
5. ONE idea only — do not overload with multiple stats
6. Tone: suggestive, not pushy — "Would you like to..." not "It's time to act"
7. End with a single yes/no question CTA
8. suppression_key format: "kind:merchant_id:YYYY-WXX"
9. Write message in ENGLISH ONLY — no Hindi, no Hinglish

GOOD EXAMPLES(do not copy exact wording):
- "Dr. Meera, 190 people in Lajpat Nagar are searching 'Dental Check Up' today. Your ₹299 offer is ready — shall I send it?"
- "Bharat, calls have dropped 50% in 7 days. Demand is strong nearby — would you like to try a targeted offer?"
- "Hi Ramesh, switching chronic patients to generic metformin could save them ~₹120/month. Shall I identify eligible patients?"

BAD EXAMPLES (avoid):
- Mixing cities: Mumbai merchant + Delhi demand data
- Pushy tone: "It's time to act now!"
- Overloaded: mentioning CTR + peer stats + patient count + savings all in one message
- Wrong name: merchant name differs from their actual business name

Return ONLY valid JSON — no markdown:
{{
  "body": "...",
  "cta": "open_ended",
  "suppression_key": "kind:merchant_id:2026-W18",
  "rationale": "one line — what trigger + why now"
}}
""",
)

compose_chain = prompt | llm | parser


# ── Helpers ───────────────────────────────────────────────────────────────────
def pick_best_trigger(merchant_payload, available_triggers, all_triggers):
    mid = merchant_payload.get("merchant_id", "")
    available_set = set(available_triggers)

    matched = [
        t for t in all_triggers
        if t.context_id in available_set
        and (t.payload.get("merchant_id") == mid or mid in t.context_id)
    ]

    if not matched:
        cat = merchant_payload.get("category_slug", "")
        matched = [t for t in all_triggers if t.context_id in available_set and cat in t.context_id]

    if not matched:
        return None

    matched.sort(key=lambda t: t.payload.get("urgency", 1), reverse=True)
    return matched[0]


def _merchant_block(m):
    p      = m.get("performance", {})
    offers = [o["title"] for o in m.get("offers", []) if o.get("status") == "active"]
    identity = m.get("identity", {})
    return (
        f"Business name: {identity.get('name')} | "
        f"Owner: {identity.get('owner_first_name')} | "
        f"City: {identity.get('city')} | "
        f"Locality: {identity.get('locality')} | "
        f"Merchant ID: {m.get('merchant_id')} | "
        f"CTR: {p.get('ctr')} | Views: {p.get('views')} | Calls: {p.get('calls')} | "
        f"7d delta: {p.get('delta_7d',{})} | "
        f"Active offers: {offers or 'none'} | "
        f"Signals: {m.get('signals',[])} | "
        f"Subscription: {m.get('subscription',{}).get('status')} "
        f"({m.get('subscription',{}).get('days_remaining','?')} days left) | "
        f"Customer aggregate: {json.dumps(m.get('customer_aggregate',{}))}"
    )


def _category_block(c):
    peer   = c.get("peer_stats", {})
    digest = c.get("digest", [{}])[0]
    return (
        f"Category: {c.get('display_name')} | "
        f"Tone: {c.get('voice',{}).get('tone')} | "
        f"Peer avg CTR: {peer.get('avg_ctr')} | "
        f"Peer avg calls: {peer.get('avg_calls_30d')} | "
        f"Top insight: {digest.get('title','')} — {digest.get('actionable','')}"
    )


def _trigger_block(t):
    p = t.payload
    return (
        f"Kind: {p.get('kind', t.context_id)} | "
        f"Urgency: {p.get('urgency', 1)} | "
        f"Merchant ID this trigger belongs to: {p.get('merchant_id','')} | "
        f"Details: {json.dumps(p)[:300]}"
    )


def _customer_block(c):
    if not c:
        return "No customer context for this trigger."
    r = c.get("relationship", {})
    return (
        f"Name: {c.get('identity',{}).get('name')} | "
        f"State: {c.get('state')} | "
        f"Last visit: {r.get('last_visit')} | "
        f"Services: {r.get('services_received', [])[-3:]}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def compose_message(merchant_payload, category_payload, trigger_obj, customer_payload=None):
    try:
        result = compose_chain.invoke({
            "merchant": _merchant_block(merchant_payload),
            "category": _category_block(category_payload),
            "trigger":  _trigger_block(trigger_obj),
            "customer": _customer_block(customer_payload),
        })

        if isinstance(result, dict):
            result["body"] = result.get("body", "")[:320]
            return result

    except Exception as e:
        logger.error(f"compose_chain failed: {e}")

    return {
        "body":            "Quick update for your business — want me to share details?",
        "cta":             "open_ended",
        "suppression_key": f"fallback:{merchant_payload.get('merchant_id','?')}:2026-W18",
        "rationale":       "LLM fallback",
    }