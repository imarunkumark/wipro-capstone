"""Production transaction processing with a full audit trail.

Runs compliance, moves money via the audited banking-api MCP tool only on
APPROVE, and records every transaction to audit_log/transactions.jsonl.
"""
import json
from pathlib import Path

from bfsi.compliance.pipeline import run_compliance
from bfsi.mcp import registry
from bfsi.model_router import route

_TXN_LOG = Path("audit_log/transactions.jsonl")


def process(request_id: str, customer_id: str, name: str,
            from_account: str, to_account: str, amount: float,
            ip_country: str = "IN") -> dict:
    route("reason", request_id)  # transaction reasoning tier
    compliance = run_compliance(customer_id, name, amount, ip_country)

    if compliance["decision"] != "APPROVE":
        result = {"request_id": request_id, "status": "REJECTED",
                  "reason": compliance.get("failed_stage"), "compliance": compliance}
    else:
        route("decide", request_id)  # money movement is highest-stakes
        xfer = registry.call("banking-api", "transfer_funds",
                             from_account=from_account, to_account=to_account,
                             amount=amount)
        result = {"request_id": request_id,
                  "status": "SETTLED" if xfer.get("ok") else "FAILED",
                  "transfer": xfer, "compliance": compliance}

    _TXN_LOG.parent.mkdir(exist_ok=True)
    with _TXN_LOG.open("a") as fh:
        fh.write(json.dumps(result) + "\n")
    return result
