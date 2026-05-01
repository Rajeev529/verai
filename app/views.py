import uuid
import time
import logging

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ContextStore
from .composer import compose_message, pick_best_trigger

logger = logging.getLogger(__name__)
START_TIME = time.time()


# ─────────────────────────────────────────────
# 1. POST /v1/context
# ─────────────────────────────────────────────
@api_view(["POST"])
def context(request):
    data       = request.data
    scope      = data.get("scope", "")
    context_id = data.get("context_id", "")
    version    = data.get("version", 1)
    payload    = data.get("payload", {})

    if not context_id or not scope:
        return Response({"error": "scope and context_id required"}, status=400)

    existing = ContextStore.objects.filter(context_id=context_id).first()

    # Idempotent: same or older version → no-op
    if existing and existing.version >= version:
        return Response({
            "accepted": True,
            "ack_id": f"ack_{uuid.uuid4().hex[:8]}",
            "stored_at": existing.stored_at.isoformat(),
        })

    obj, _ = ContextStore.objects.update_or_create(
        context_id=context_id,
        defaults={"scope": scope, "version": version, "payload": payload},
    )

    return Response({
        "accepted": True,
        "ack_id": f"ack_{uuid.uuid4().hex[:8]}",
        "stored_at": obj.stored_at.isoformat(),
    })


# ─────────────────────────────────────────────
# 2. POST /v1/tick
# ─────────────────────────────────────────────
@api_view(["POST"])
def tick(request):
    available_triggers = request.data.get("available_triggers", [])
    actions = []

    merchants   = ContextStore.objects.filter(scope="merchant")[:20]
    all_triggers = list(ContextStore.objects.filter(scope="trigger"))

    for merchant in merchants:
        if len(actions) >= 20:
            break

        m_payload = merchant.payload
        cat_slug  = m_payload.get("category_slug", "")

        # Load category context
        cat_obj = ContextStore.objects.filter(scope="category", context_id=cat_slug).first()
        cat_payload = cat_obj.payload if cat_obj else {"display_name": cat_slug, "voice": {}, "peer_stats": {}, "digest": []}

        # Pick best trigger
        best_trigger = pick_best_trigger(m_payload, available_triggers, all_triggers)
        if not best_trigger:
            continue

        # Load optional customer context
        cust_payload = None
        cust_id = best_trigger.payload.get("customer_id")
        if cust_id:
            cust_obj = ContextStore.objects.filter(scope="customer", context_id=cust_id).first()
            if cust_obj:
                cust_payload = cust_obj.payload

        try:
            msg = compose_message(m_payload, cat_payload, best_trigger, cust_payload)
            actions.append({
                "merchant_id":     merchant.context_id,
                "trigger_id":      best_trigger.context_id,
                "body":            msg["body"][:320],
                "cta":             msg.get("cta", "open_ended"),
                "suppression_key": msg.get("suppression_key", f"{best_trigger.context_id}:default"),
            })
        except Exception as e:
            logger.error(f"Compose failed for {merchant.context_id}: {e}")
            continue

    return Response({"actions": actions})


# ─────────────────────────────────────────────
# 3. POST /v1/reply
# ─────────────────────────────────────────────
@api_view(["POST"])
def reply(request):
    message     = request.data.get("message", "").lower()
    turn_number = request.data.get("turn_number", 1)

    positive = ["yes", "haan", "ok", "sure", "send", "draft", "go", "please", "kar", "karo", "bhejo", "acha"]
    negative = ["no", "nahi", "nope", "later", "stop", "cancel", "mat", "ruko", "hold"]

    if any(w in message for w in positive):
        body = "Sending now! I'll also prepare a follow-up for non-responders." if turn_number <= 2 \
               else "Done — campaign live. I'll share performance in 24 hours."
        return Response({
            "action":    "send",
            "body":      body,
            "rationale": "Merchant accepted — proceeding with action",
        })

    if any(w in message for w in negative):
        return Response({
            "action":    "end",
            "body":      "",
            "rationale": "Merchant declined — closing session cleanly",
        })

    # Unclear / question
    return Response({
        "action":    "wait",
        "body":      "Got it — should I go ahead and send, or would you like to review first?",
        "rationale": "Intent unclear — asking single clarifying question",
    })


# ─────────────────────────────────────────────
# 4. GET /v1/healthz
# ─────────────────────────────────────────────
@api_view(["GET"])
def healthz(request):
    counts = {
        scope: ContextStore.objects.filter(scope=scope).count()
        for scope in ["category", "merchant", "customer", "trigger"]
    }
    return Response({
        "status":          "ok",
        "uptime_seconds":  int(time.time() - START_TIME),
        "contexts_loaded": counts,
    })


# ─────────────────────────────────────────────
# 5. GET /v1/metadata
# ─────────────────────────────────────────────
@api_view(["GET"])
def metadata(request):
    return Response({
        "team_name":    "Your Name Here",
        "team_members": ["Your Name Here"],
        "model":        "claude-sonnet-4-20250514",
        "approach":     "4-layer structured prompt composer — merchant + category + trigger + customer injected directly into LLM prompt. No vector DB needed; data already structured JSON.",
        "version":      "1.0.0",
    })