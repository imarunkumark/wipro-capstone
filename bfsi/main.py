"""Heritage National Bank AI Platform — entry point.

Runs an end-to-end banking workflow across all integrated layers. This is the
file /security-review targets in Phase 6.
"""
from dotenv import load_dotenv

from bfsi.transactions import process
from bfsi.batch_fraud import run_batch

load_dotenv()


def main():
    print("=== End-to-end banking workflow ===")
    settled = process("R1001", "C5001", "Asha Rao",
                      from_account="AC5001", to_account="AC5002",
                      amount=750.0, ip_country="IN")
    print("  R1001:", settled["status"])

    blocked = process("R1002", "C5002", "Ivan Petrov",
                      from_account="AC5002", to_account="AC5001",
                      amount=5000.0, ip_country="RU")
    print("  R1002:", blocked["status"], "->", blocked.get("reason"))

    print("=== Batch fraud pipeline ===")
    for r in run_batch():
        print(f"  {r['id']}: risk={r['risk']} ({r['engine']})")


if __name__ == "__main__":
    main()
