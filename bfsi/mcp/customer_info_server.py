"""customer-info MCP server: customer master data, history, and IP checks.

Exposes the fraud tool-use functions the chatbot relies on:
check_customer_history and verify_ip_location.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("customer-info")

_CUSTOMERS = {
    "C5001": {"name": "Asha Rao",  "kyc_verified": True,  "tier": "retail",
              "home_country": "IN", "risk": "low"},
    "C5002": {"name": "Liam Chen", "kyc_verified": True,  "tier": "premier",
              "home_country": "SG", "risk": "low"},
}
_HISTORY = {
    "C5001": [{"amount": 250.0, "country": "IN"}, {"amount": 900.0, "country": "IN"}],
    "C5002": [{"amount": 12000.0, "country": "SG"}],
}


@mcp.tool()
def get_customer(customer_id: str) -> dict:
    """Return the customer master record."""
    c = _CUSTOMERS.get(customer_id)
    return c | {"customer_id": customer_id} if c else {"error": "not_found"}


@mcp.tool()
def check_customer_history(customer_id: str) -> dict:
    """Fraud tool-use: return prior transaction history for baselining."""
    hist = _HISTORY.get(customer_id, [])
    avg = round(sum(h["amount"] for h in hist) / len(hist), 2) if hist else 0.0
    return {"customer_id": customer_id, "count": len(hist), "avg_amount": avg}


@mcp.tool()
def verify_ip_location(customer_id: str, ip_country: str) -> dict:
    """Fraud tool-use: flag if the request country != the customer home country."""
    home = _CUSTOMERS.get(customer_id, {}).get("home_country")
    mismatch = home is not None and ip_country != home
    return {"customer_id": customer_id, "home_country": home,
            "ip_country": ip_country, "geo_mismatch": mismatch}


if __name__ == "__main__":
    mcp.run()
