"""Performance optimization via model routing.

Route each request to the cheapest capable model and LOG the rationale to
audit_log/model_routing.jsonl, as required by CLAUDE.md.
"""
import json
import os
from pathlib import Path

_LOG = Path("audit_log/model_routing.jsonl")

_TIERS = {
    "classify": ("MODEL_HAIKU", "anthropic/claude-3.5-haiku",
                 "high-volume, low-stakes classification"),
    "reason":   ("MODEL_SONNET", "anthropic/claude-sonnet-4.5",
                 "default reasoning: chatbot, KYC, compliance narrative"),
    "decide":   ("MODEL_OPUS", "anthropic/claude-opus-4.1",
                 "highest-stakes decision: final approval / judge / ambiguous fraud"),
}


def route(task: str, request_id: str) -> str:
    """Return the model slug for a task class and log the rationale."""
    env, default, reason = _TIERS.get(task, _TIERS["reason"])
    model = os.environ.get(env, default)
    _LOG.parent.mkdir(exist_ok=True)
    with _LOG.open("a") as fh:
        fh.write(json.dumps({"request_id": request_id, "task": task,
                             "model": model, "rationale": reason}) + "\n")
    return model
