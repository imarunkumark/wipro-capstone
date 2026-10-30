"""Compliance-guardrailed customer service chatbot.

Advanced prompting via the cached customer-support skill; input sanitization;
streaming responses; and fraud tool-use (check_customer_history / verify_ip_location)
through the audited MCP registry.
"""
import os
import re

from anthropic import Anthropic
from bfsi.mcp import registry
from bfsi.skills_loader import build_cached_system

_BANNED = re.compile(r"(ignore\s+previous|system\s+prompt|full\s+card\s+number)", re.I)


def sanitize(text: str) -> str:
    """PCI DSS input sanitization: strip control chars and prompt-injection bait."""
    text = "".join(ch for ch in text if ch.isprintable())
    return _BANNED.sub("[removed]", text)[:2000]


def fraud_tools(customer_id: str, ip_country: str) -> dict:
    """Fetch fraud signals via the audited MCP tools."""
    return {
        "history": registry.call("customer-info", "check_customer_history",
                                 customer_id=customer_id),
        "geo": registry.call("customer-info", "verify_ip_location",
                             customer_id=customer_id, ip_country=ip_country),
    }


def reply(customer_id: str, message: str, ip_country: str = "IN",
          stream: bool = True) -> str:
    clean = sanitize(message)
    signals = fraud_tools(customer_id, ip_country)
    client = Anthropic(auth_token=os.environ["OPENROUTER_API_KEY"],
                       base_url=os.environ.get("ANTHROPIC_BASE_URL",
                                               "https://openrouter.ai/api"))
    user = f"Customer {customer_id} asks: {clean}\nFraud signals: {signals}"
    kwargs = dict(model=os.environ.get("MODEL_SONNET", "anthropic/claude-sonnet-4.5"),
                  max_tokens=300, system=build_cached_system(["customer-support"]),
                  messages=[{"role": "user", "content": user}])
    out = []
    if stream:
        with client.messages.stream(**kwargs) as s:
            for chunk in s.text_stream:
                out.append(chunk)
    else:
        resp = client.messages.create(**kwargs)
        out.append("".join(b.text for b in resp.content if b.type == "text"))
    return "".join(out)
