"""Sanctions screening against a demo watchlist.

Returns a match record the sanctions-summary skill can escalate. Real systems
screen against OFAC/UN/EU consolidated lists; the interface is identical.
"""
_WATCHLIST = {"ivan petrov", "acme shell holdings", "redline logistics"}


def sanctions_check(name: str) -> dict:
    """Return {"name","hit","strength"} for a normalized name match."""
    n = " ".join(name.lower().split())
    exact = n in _WATCHLIST
    partial = any(n in w or w in n for w in _WATCHLIST) and not exact
    strength = "STRONG" if exact else ("PARTIAL" if partial else "NONE")
    return {"name": name, "hit": strength != "NONE", "strength": strength}
