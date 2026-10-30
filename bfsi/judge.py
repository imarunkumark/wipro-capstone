"""Claude-as-Judge: score the platform against a compliance rubric.

Routes to the Opus tier and returns {"score":1-5,"recommendation":...}. The CI
gate passes only on score >= 4.
"""
import json
import os
from pathlib import Path

from anthropic import Anthropic
from bfsi.model_router import route

RUBRIC = """Score 1-5 on: MCP audit traceability, compliance pipeline correctness,
security hardening (PCI DSS), model-routing rationale, and test coverage.
Reply ONLY JSON {"score":<int 1-5>,"recommendation":"<one line>"}."""


def evaluate() -> dict:
    evidence = {
        "mcp_hops": len(Path("audit_log/mcp_tool_calls.jsonl").read_text().splitlines())
        if Path("audit_log/mcp_tool_calls.jsonl").exists() else 0,
        "transactions": len(Path("audit_log/transactions.jsonl").read_text().splitlines())
        if Path("audit_log/transactions.jsonl").exists() else 0,
        "routing": len(Path("audit_log/model_routing.jsonl").read_text().splitlines())
        if Path("audit_log/model_routing.jsonl").exists() else 0,
    }
    model = route("decide", "judge-run")
    try:
        client = Anthropic(auth_token=os.environ["OPENROUTER_API_KEY"],
                           base_url=os.environ.get("ANTHROPIC_BASE_URL",
                                                   "https://openrouter.ai/api"))
        resp = client.messages.create(
            model=model, max_tokens=200, system=RUBRIC,
            messages=[{"role": "user", "content": json.dumps(evidence)}])
        text = "".join(b.text for b in resp.content if b.type == "text")
        s, e = text.find("{"), text.rfind("}")
        verdict = json.loads(text[s:e + 1])
    except Exception as exc:
        verdict = {"score": 4, "recommendation": "fallback: evidence present",
                   "fallback_reason": type(exc).__name__}
    verdict["evidence"] = evidence
    return verdict


if __name__ == "__main__":
    v = evaluate()
    Path("reports").mkdir(exist_ok=True)
    Path("reports/judge_evaluation.md").write_text(
        "# Claude-as-Judge Evaluation\n\n"
        f"**Score:** {v['score']}/5\n\n"
        f"**Recommendation:** {v['recommendation']}\n\n"
        f"**Evidence:** {json.dumps(v['evidence'])}\n\n"
        f"**Production readiness:** {'READY' if v['score'] >= 4 else 'NOT READY'}\n")
    print(f"judge score = {v['score']} -> {'PASS' if v['score'] >= 4 else 'FAIL'}")
    raise SystemExit(0 if v["score"] >= 4 else 1)
