"""Vision-based KYC: extract identity fields from a document.

In the lab we pass a text description of the document to the kyc-extraction
skill (the same call shape supports an image block in production).
"""
import json
import os

from anthropic import Anthropic
from bfsi.skills_loader import build_cached_system


def extract_identity(doc_text: str) -> dict:
    client = Anthropic(auth_token=os.environ["OPENROUTER_API_KEY"],
                       base_url=os.environ.get("ANTHROPIC_BASE_URL",
                                               "https://openrouter.ai/api"))
    try:
        resp = client.messages.create(
            model=os.environ.get("MODEL_SONNET", "anthropic/claude-sonnet-4.5"),
            max_tokens=200, system=build_cached_system(["kyc-extraction"]),
            messages=[{"role": "user", "content": doc_text}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1]) | {"engine": "claude"}
    except Exception as exc:
        return {"full_name": "UNKNOWN", "doc_type": "UNKNOWN", "doc_number": "****",
                "expiry": "UNKNOWN", "engine": "fallback",
                "fallback_reason": type(exc).__name__}
