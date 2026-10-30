"""Submit synthetic batch transactions through the fraud pipeline.

Emulates the Module 5 Batch API: score many transactions at the Haiku tier and
log the model-selection rationale for each routed request.
"""
import json
from pathlib import Path

from bfsi.fraud_engine import score_transaction
from bfsi.model_router import route

_SYNTHETIC = [
    {"id": "B1", "customer_id": "C5001", "amount": 300.0,   "ip_country": "IN"},
    {"id": "B2", "customer_id": "C5001", "amount": 9000.0,  "ip_country": "RU"},
    {"id": "B3", "customer_id": "C5002", "amount": 15000.0, "ip_country": "SG"},
    {"id": "B4", "customer_id": "C5002", "amount": 60000.0, "ip_country": "NG"},
]


def run_batch() -> list[dict]:
    out = []
    for tx in _SYNTHETIC:
        route("classify", tx["id"])  # batch scoring -> Haiku tier, logged
        score = score_transaction(tx["customer_id"], tx["amount"], tx["ip_country"])
        out.append({"id": tx["id"], "risk": score["risk"], "engine": score["engine"]})
    Path("audit_log").mkdir(exist_ok=True)
    Path("audit_log/batch_results.json").write_text(json.dumps(out, indent=2))
    return out
