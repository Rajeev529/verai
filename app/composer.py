import os
import json
import logging
from datetime import datetime

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
Compose ONE sharp WhatsApp nudge that makes the merchant WANT to reply immediately.

MERCHANT CONTEXT:
{merchant}

CATEGORY CONTEXT:
{category}

TRIGGER CONTEXT:
{trigger}

CUSTOMER CONTEXT:
{customer}

STRICT RULES:
1. Max 320 characters
2. English ONLY — no Hindi, no Hinglish
3. Use merchant's EXACT business name and owner name
4. Use merchant's OWN city/locality ONLY — never mix cities
5. ONE idea only — single insight, single benefit, single CTA
6. Use SPECIFIC numbers: exact offer price, exact customer count, exact days
7. No rupee symbol — use "Rs." instead
8. End with ONE yes/no question
9. Use suppression_key exactly as provided in TRIGGER CONTEXT

MESSAGE STRUCTURE (follow exactly):
[Owner name], [specific fact with number] — [one clear benefit]. [Single yes/no question]?

ENGAGEMENT COMPULSION TECHNIQUES (pick one):
1. FOMO: "X people searched today — act before weekend"
2. Loss aversion: "calls dropped from X to Y this week"
3. Time pressure: "before tonight", "in the next 2 hours", "before weekend"
4. Personal stake: use customer name + specific detail if available
5. Easy win: "just say yes, I'll handle everything"

EXAMPLES BY TRIGGER KIND:
- perf_dip: "Bharat, calls dropped from 12 to 6 this week. One targeted offer could recover that — want me to try today?"
- research_digest: "Dr. Meera, 190 people searched 'dental checkup' in Lajpat Nagar today — your Rs.299 offer is live. Shall I reach them before tonight?"
- ipl: "Suresh, DC vs MI starts in 3 hours. 180 fans near Sant Nagar — shall I push your BOGO pizza deal right now?"
- winback: "Karthik, Rashmi hasn't visited PowerHouse in 57 days. Her focus was weight loss — want me to send her a personal nudge today?"
- supply_alert: "Ramesh, 2 atorvastatin batches recalled — your 240 chronic patients need a heads up. Shall I alert them before the weekend?"
- chronic_refill: "Ramesh, Mr. Sharma's metformin runs out in 3 days — shall I send a refill reminder with free home delivery today?"
- renewal_due: "Bharat, your Pro plan expires in 12 days — after that, your listing drops in search. Renew now to keep your 18 calls/month?"
- recall_due: "Dr. Meera, Priya's 6-month cleaning is due this week. She visited 4x last year — shall I send her a slot for Wed or Thu?"

LOW COMPULSION (never do these):
- "Your CTR is below peer average. Would you like to improve it?"
- "There is demand in your area. Should I help?"
- Mentioning 3+ stats in one message
- Generic CTAs: "Want to grow your business?"

Return ONLY valid JSON:
{{
  "body": "...",
  "cta": "open_ended",
  "suppression_key": "...",
  "rationale": "trigger kind + specific reason why now"
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
        and t.payload.get("merchant_id") == mid
    ]

    if not matched:
        cat = merchant_payload.get("category_slug", "")
        matched = [
            t for t in all_triggers
            if t.context_id in available_set
            and cat in t.context_id
            and t.payload.get("merchant_id", mid) == mid
        ]

    if not matched:
        return None

    matched.sort(key=lambda t: t.payload.get("urgency", 1), reverse=True)
    return matched[0]


def _clean_offer(offer):
    return offer.replace("₹", "Rs.").replace("@", "at")


def _merchant_block(m):
    p        = m.get("performance", {})
    offers   = [_clean_offer(o["title"]) for o in m.get("offers", []) if o.get("status") == "active"]
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


def _trigger_block(t, p):
    kind = p.get("kind", t.context_id)
    mid  = p.get("merchant_id", "")
    supp = p.get("suppression_key", f"{kind}:{mid}:2026-W18")
    return (
        f"Kind: {kind} | "
        f"Urgency: {p.get('urgency', 1)} | "
        f"Merchant ID: {mid} | "
        f"suppression_key to use exactly: {supp} | "
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


# ── Festival override ─────────────────────────────────────────────────────────
def _festival_message(merchant_payload, p):
    identity   = merchant_payload.get("identity", {})
    owner      = identity.get("owner_first_name", "")
    offers     = [_clean_offer(o["title"]) for o in merchant_payload.get("offers", []) if o.get("status") == "active"]
    best_offer = offers[0] if offers else "your best offer"
    cust_agg   = merchant_payload.get("customer_aggregate", {})
    lapsed     = (
        cust_agg.get("lapsed_90d_plus")
        or cust_agg.get("lapsed_180d_plus")
        or cust_agg.get("lapsed_customers_added_since_expiry")
        or 0
    )
    festival = p.get("festival", "festive season")
    mid      = merchant_payload.get("merchant_id", "")
    supp     = p.get("suppression_key", f"festival_upcoming:{mid}:2026-W18")

    if lapsed:
        body = f"{owner}, festive season bookings fill fast. You have {lapsed} lapsed clients — shall I reach them this week with your {best_offer}?"
    else:
        body = f"{owner}, {festival} prep starts now. Your {best_offer} is perfect for early bookings — shall I run a campaign this week?"

    return {
        "body":            body[:320],
        "cta":             "open_ended",
        "suppression_key": supp,
        "rationale":       "Festival >30 days away — reactivate lapsed clients now",
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def compose_message(merchant_payload, category_payload, trigger_obj, customer_payload=None):
    p = trigger_obj.payload
    if "payload" in p:
        p = {**p, **p["payload"]}

    kind = p.get("kind", "")

    days_until = p.get("days_until", 0)
    if not days_until and p.get("date"):
        try:
            festival_date = datetime.fromisoformat(p["date"])
            days_until = (festival_date - datetime.now()).days
        except:
            days_until = 0

    if kind == "festival_upcoming" and days_until > 30:
        return _festival_message(merchant_payload, p)

    try:
        result = compose_chain.invoke({
            "merchant": _merchant_block(merchant_payload),
            "category": _category_block(category_payload),
            "trigger":  _trigger_block(trigger_obj, p),
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