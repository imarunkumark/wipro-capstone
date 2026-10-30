# Compliance Report: Heritage National Bank AI Banking Platform (Capstone)

**Sources:** `audit_log/mcp_tool_calls.jsonl` (35 records), `audit_log/transactions.jsonl` (4 records), `audit_log/model_routing.jsonl` (10 records), checked against the constraints in `CLAUDE.md`.
**Prepared by:** compliance-doc sub-agent, 2026-10-30.

> **Scope caveat:** The logs mix test runs with demo or production-style runs. `REDGE` (edge case: a 10,000,000.00 transfer) and `RAUD` (audit check) are test request IDs. `B1` to `B4` are batch classification runs. The MCP log has no `request_id`, and its `seq` counter restarts at 1 four times, so it covers at least 4 separate runs or sessions. You cannot tie MCP hops to a specific transaction from the log alone.

---

## 1. MCP Hops

### Counts per server / tool

| Server        | Tool                   | Calls | ok=true |
|---------------|------------------------|------:|--------:|
| customer-info | get_customer           | 8     | 8       |
| customer-info | check_customer_history | 11    | 11      |
| customer-info | verify_ip_location     | 11    | 11      |
| banking-api   | get_balance            | 2     | 2       |
| banking-api   | transfer_funds         | 3     | 3       |
| github        | (none)                 | 0     | 0       |
| **Total**     |                        | **35**| **35**  |

- **By server:** customer-info has 30 calls and banking-api has 5. The github server has none.
- **Not called:** `get_account`, `apply_loan` and all github tools appear nowhere in the log.
- **Failures:** none. Every call returned `ok: true`.

### Sessions (inferred from `seq` resets)

| Session | Calls | Notable hops |
|---------|------:|--------------|
| 1 | 3  | get_customer C5001, get_balance AC5001, transfer_funds AC5001 -> AC5002 750.00 |
| 2 | 3  | Customer lookup, history and IP check (C5001, IN). No money movement. |
| 3 | 15 | Customer C5001 checks, then transfer_funds 750.00 (seq 4). Next, C5002 checks with IPs RU, SG and NG, plus repeated C5001 checks (IN, RU). |
| 4 | 14 | get_balance AC5001, several C5001/C5002 checks, then transfer_funds 10.00 (seq 14, matches `RAUD`). |

**About the transfers:** The log shows three `transfer_funds` calls, but `transactions.jsonl` records only two SETTLED transfers: R1001 for 750.00 and RAUD for 10.00. The 750.00 transfer was called twice (sessions 1 and 3). Because the MCP log has no request ID, it cannot show which call belongs to R1001. The other 750.00 call has no matching entry in the transaction audit trail.

---

## 2. Transaction Outcomes

| request_id | Test? | Status   | Decision | Failed stage | Stages run (in order)                          | Fraud risk (engine)   | Amount        |
|------------|-------|----------|----------|--------------|------------------------------------------------|-----------------------|---------------|
| R1001      | No    | SETTLED  | APPROVE  | none         | KYC ok -> AML ok (LOW) -> SANCTIONS ok (NONE) -> APPROVAL ok | LOW (fallback)  | 750.00        |
| R1002      | No    | REJECTED | BLOCK    | **AML**      | KYC ok -> AML fail (HIGH)                      | HIGH (fallback)       | 5,000.00      |
| REDGE      | Yes   | REJECTED | BLOCK    | **AML**      | KYC ok -> AML fail (HIGH)                      | HIGH (fallback)       | 10,000,000.00 |
| RAUD       | Yes   | SETTLED  | APPROVE  | none         | KYC ok -> AML ok (LOW) -> SANCTIONS ok (NONE) -> APPROVAL ok | LOW (fallback)  | 10.00         |

- **Summary:** 2 transfers settled and 2 were rejected, both at the AML stage. No transaction reached a Sanctions or Approval block.
- **R1002:** AML rated it HIGH because of the geo mismatch, even though the amount (5,000) is below the customer's average (12,000).
- **REDGE:** AML rated it HIGH because the amount is about 17,000 times the customer's average.
- **Fraud scoring used the fallback rule every time.** In all 4 records, `engine` is `fallback` and `fallback_reason` is `NotFoundError`. The model-based fraud scorer never ran successfully, so every risk rating came from the rule-based fallback. This should be fixed before production.
- **Balances reset between runs.** `from_balance` is 4250.00 for R1001 and 4990.00 for RAUD, so both started from 5000.00. Each run began from a fresh fixture.

---

## 3. Model Routing Rationale

| Task     | Model                        | Count | Request IDs                      | Logged rationale |
|----------|------------------------------|------:|----------------------------------|------------------|
| reason   | anthropic/claude-sonnet-4.5  | 4     | R1001, R1002, REDGE, RAUD        | "default reasoning: chatbot, KYC, compliance narrative" |
| decide   | anthropic/claude-opus-4.1    | 2     | R1001, RAUD                      | "highest-stakes decision: final approval / judge / ambiguous fraud" |
| classify | anthropic/claude-3.5-haiku   | 4     | B1, B2, B3, B4                   | "high-volume, low-stakes classification" |
| **Total**|                              | **10**|                                  | |

- **Matches the CLAUDE.md policy.** Haiku handles classification, Sonnet handles default reasoning, and Opus handles final decisions.
- **Opus runs only for approved transactions.** The `decide` (Opus) step appears only for R1001 and RAUD, which reached the APPROVAL stage. The blocked R1002 and REDGE stopped at AML and never reached Opus. This is the expected behaviour.
- **Every request has a rationale.** Each routing record includes one.
- **No timestamps.** No routing record has a timestamp.

---

## 4. Evaluation Against CLAUDE.md Constraints

| # | CLAUDE.md requirement | Evidence in logs | Assessment |
|---|-----------------------|------------------|------------|
| 1 | Never log full PAN; mask to last 4 | No 13-19 digit numbers in any log. Only account IDs (AC5001/AC5002) and customer IDs appear. | **Pass (no violation found).** No card or PAN flow was exercised, so the logs never show masking in action. |
| 2 | Sanitize all chatbot/user input | No input-sanitization records. | **No evidence.** |
| 3 | Per-session rate limiting on money movement | No rate-limit records, counters or throttle/deny events. Session 3 ran a transfer without being throttled. | **No evidence.** The logs cannot show this control is enforced. |
| 4 | Audit money movement and compliance decisions (who/what/when) | **What:** recorded (tool, args, decision, stages). **Who:** no actor, user or session ID. **When:** no timestamps in any of the three logs. | **Partial.** "Who" and "when" are missing. The third 750.00 `transfer_funds` call has no matching transaction record. |
| 5 | Secrets from env vars only | Nothing in the audit logs (and none should be). | **Not assessable from the logs.** No secrets appear in them. |
| 6 | Every MCP hop audited (PreToolUse hook) | 35 hops were logged with server, tool, args and ok. | **Partial.** Hops are logged, but they have no request ID or timestamp, so you cannot tie them to transactions. |
| 7 | Log routing rationale for every request | All 10 routing records have a rationale. Every transaction ID has at least one routing record. | **Pass.** Timestamps are missing. |
| 8 | Pipeline order KYC -> AML -> Sanctions -> Approval; BLOCK stops and is audited | All 4 transactions run the stages in the correct order. Both BLOCKs stop right after the failing AML stage, and Sanctions and Approval do not run. Both are recorded with `failed_stage`. | **Pass.** |
| 9 | Definition of Done: bandit or pytest results | `bandit_scan.txt` and `batch_results.json` exist but were outside the scope of this review. | **Not evaluated here.** |

### Other observations
- **Customer name in logs.** The transaction log records a customer name (`"Asha Rao"`) in the sanctions result. This is not PAN data, but it is PII in an audit log. Check it against the data-retention and minimization policy.
- **Possible missing balance check.** `get_balance` was not called before the `transfer_funds` calls in sessions 3 and 4. Session 4 did call it at the start of the session. The pipeline may rely on other checks; confirm that the balance is checked before money moves.

## 5. Recommendations
1. Add `request_id`, `session_id`/actor and an ISO-8601 timestamp to every record in all three audit logs. This meets "who/what/when" and lets you tie MCP hops to transactions.
2. Emit audit events for rate-limit checks and input sanitization. Right now these PCI DSS controls cannot be verified.
3. Fix the fraud-model `NotFoundError`. It is likely a bad model ID or endpoint, and it forced the rule-based fallback every time.
4. Separate test traffic (REDGE, RAUD, B*) from the production audit trail, or tag it as test traffic.
5. Find out why `transfer_funds` for 750.00 appears twice in the MCP log but only once in `transactions.jsonl`.
