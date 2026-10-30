"""In-process MCP registry with audit tracing.

Routes call(server, tool, args) to the right handler and appends every hop to
audit_log/mcp_tool_calls.jsonl so end-to-end transactions are fully traceable.
"""
import json
from pathlib import Path

from bfsi.mcp import customer_info_server as cinfo
from bfsi.mcp import banking_api_server as bank

_AUDIT = Path("audit_log/mcp_tool_calls.jsonl")
_SEQ = {"n": 0}

_TOOLS = {
    ("customer-info", "get_customer"): cinfo.get_customer,
    ("customer-info", "check_customer_history"): cinfo.check_customer_history,
    ("customer-info", "verify_ip_location"): cinfo.verify_ip_location,
    ("banking-api", "get_balance"): bank.get_balance,
    ("banking-api", "transfer_funds"): bank.transfer_funds,
    ("banking-api", "apply_loan"): bank.apply_loan,
}


def _mask(args: dict) -> dict:
    """PCI DSS: never audit full card numbers — mask to last 4."""
    out = dict(args)
    for k, v in out.items():
        if "card" in k.lower() and isinstance(v, str) and len(v) > 4:
            out[k] = "****" + v[-4:]
    return out


def _audit(server, tool, args, result):
    _AUDIT.parent.mkdir(exist_ok=True)
    _SEQ["n"] += 1
    rec = {"seq": _SEQ["n"], "server": server, "tool": tool,
           "args": _mask(args), "ok": "error" not in (result or {})}
    with _AUDIT.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def call(server: str, tool: str, **args) -> dict:
    """Call an MCP tool and record the hop to the audit log."""
    fn = _TOOLS.get((server, tool))
    if fn is None:
        raise KeyError(f"unknown MCP tool {server}.{tool}")
    result = fn(**args)
    _audit(server, tool, args, result)
    return result
