"""Fraud detection engine: combines MCP signals with a skill-based opinion."""
import json
import os

from anthropic import Anthropic
from bfsi.mcp import registry
from bfsi.skills_loader import build_cached_system


def _client():
    return Anthropic(auth_token=os.environ["OPENROUTER_API_KEY"],
                     base_url=os.environ.get("ANTHROPIC_BASE_URL",
                                             "https://openrouter.ai/api"))


def score_transaction(customer_id: str, amount: float, ip_country: str) -> dict:
    """Return {"risk","reason","signals"} using history + geo + fraud-triage skill."""
    hist = registry.call("customer-info", "check_customer_history",
                         customer_id=customer_id)
    geo = registry.call("customer-info", "verify_ip_location",
                        customer_id=customer_id, ip_country=ip_country)
    signals = {"amount": amount, "avg_amount": hist["avg_amount"],
               "geo_mismatch": geo["geo_mismatch"]}
    try:
        resp = _client().messages.create(
            model=os.environ.get("MODEL_HAIKU", "anthropic/claude-3.5-haiku"),
            max_tokens=150, system=build_cached_system(["fraud-triage"]),
            messages=[{"role": "user", "content": json.dumps(signals)}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        s, e = text.find("{"), text.rfind("}")
        out = json.loads(text[s:e + 1]); out["engine"] = "claude"
    except Exception as exc:
        big = amount > max(hist["avg_amount"] * 3, 5000)
        risk = "HIGH" if (big or geo["geo_mismatch"]) else "LOW"
        out = {"risk": risk, "reason": "fallback rule", "engine": "fallback",
               "fallback_reason": type(exc).__name__}
    out["signals"] = signals
    return out
