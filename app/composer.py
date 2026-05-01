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

# ── LLM + Chain (OpenRouter) ──────────────────────────────────────────────────
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
Compose ONE sharp outbound message using the context below.

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
2. Use REAL numbers from context — name, CTR, offer price, customer count
3. No URLs in body
4. Exactly ONE clear CTA (yes/no question or single action)
5. Do NOT be generic — always mention merchant name + one specific fact
6. Match the tone from CATEGORY CONTEXT

Return ONLY a valid JSON object — no markdown, no extra text:
{{
  "body": "...",
  "cta": "open_ended",
  "suppression_key": "...",
  "rationale": "one line why this message now"
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
    return (
        f"Name: {m.get('identity',{}).get('name')} | "
        f"Owner: {m.get('identity',{}).get('owner_first_name')} | "
        f"City: {m.get('identity',{}).get('city')} | "
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
        f"Peer avg CTR: {peer.get('avg_ctr')} | Peer avg calls: {peer.get('avg_calls_30d')} | "
        f"Top insight: {digest.get('title','')} — {digest.get('actionable','')}"
    )


def _trigger_block(t):
    p = t.payload
    return (
        f"Kind: {p.get('kind', t.context_id)} | "
        f"Urgency: {p.get('urgency', 1)} | "
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
        "suppression_key": f"fallback:{merchant_payload.get('merchant_id','?')}",
        "rationale":       "LLM fallback",
    }