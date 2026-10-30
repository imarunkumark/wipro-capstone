"""banking-api MCP server: accounts, balances, transfers, loans."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("banking-api")

_ACCOUNTS = {
    "AC5001": {"customer_id": "C5001", "balance": 5000.0},
    "AC5002": {"customer_id": "C5002", "balance": 42000.0},
}


@mcp.tool()
def get_balance(account_id: str) -> dict:
    """Return the current account balance."""
    a = _ACCOUNTS.get(account_id)
    return {"account_id": account_id, "balance": a["balance"]} if a else {"error": "not_found"}


@mcp.tool()
def transfer_funds(from_account: str, to_account: str, amount: float) -> dict:
    """Move money between two accounts (validated, non-negative balances)."""
    src, dst = _ACCOUNTS.get(from_account), _ACCOUNTS.get(to_account)
    if not src or not dst:
        return {"ok": False, "error": "account_not_found"}
    if src["balance"] < amount:
        return {"ok": False, "error": "insufficient_funds"}
    src["balance"] -= amount
    dst["balance"] += amount
    return {"ok": True, "from": from_account, "to": to_account,
            "amount": amount, "from_balance": round(src["balance"], 2)}


@mcp.tool()
def apply_loan(customer_id: str, amount: float, term_months: int) -> dict:
    """Return an indicative loan decision (demo underwriting rule)."""
    approved = amount <= 25000
    return {"customer_id": customer_id, "amount": amount, "term_months": term_months,
            "decision": "APPROVED" if approved else "REFERRED"}


if __name__ == "__main__":
    mcp.run()
