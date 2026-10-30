"""Compliance automation pipeline: KYC -> AML -> Sanctions -> Approval.

A transaction advances only if the prior stage passes; any BLOCK stops the
pipeline and is returned with the failing stage for audit.
"""
from bfsi.mcp import registry
from bfsi.compliance.sanctions_check import sanctions_check
from bfsi.fraud_engine import score_transaction


def run_compliance(customer_id: str, name: str, amount: float,
                   ip_country: str) -> dict:
    stages = []

    # KYC
    cust = registry.call("customer-info", "get_customer", customer_id=customer_id)
    kyc_ok = cust.get("kyc_verified") is True
    stages.append({"stage": "KYC", "ok": kyc_ok})
    if not kyc_ok:
        return {"decision": "BLOCK", "failed_stage": "KYC", "stages": stages}

    # AML (fraud engine as the AML risk signal)
    fraud = score_transaction(customer_id, amount, ip_country)
    aml_ok = fraud["risk"] != "HIGH"
    stages.append({"stage": "AML", "ok": aml_ok, "risk": fraud["risk"]})
    if not aml_ok:
        return {"decision": "BLOCK", "failed_stage": "AML",
                "stages": stages, "fraud": fraud}

    # Sanctions
    sanc = sanctions_check(name)
    sanc_ok = not sanc["hit"] or sanc["strength"] == "PARTIAL"
    stages.append({"stage": "SANCTIONS", "ok": sanc_ok, "strength": sanc["strength"]})
    if not sanc_ok:
        return {"decision": "BLOCK", "failed_stage": "SANCTIONS",
                "stages": stages, "sanctions": sanc}

    # Approval
    stages.append({"stage": "APPROVAL", "ok": True})
    return {"decision": "APPROVE", "stages": stages, "fraud": fraud, "sanctions": sanc}
