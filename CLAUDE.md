# Heritage National Bank — AI Banking Platform (Capstone)

Authoritative development context for Claude Code. Read this before any change.

## Project
Unified, production-ready AI banking platform integrating Skills, MCP servers,
chatbot, fraud detection, compliance automation, transaction processing,
microservices, performance optimization, and security hardening.

## MCP Registry (see .claude/mcp.json)
| Server        | Purpose                                  | Key tools |
|---------------|------------------------------------------|-----------|
| customer-info | Customer master data & history           | get_customer, check_customer_history, verify_ip_location |
| banking-api   | Accounts, balances, transfers, loans     | get_balance, transfer_funds, get_account, apply_loan |
| github        | Branch / commit / pull request           | create_branch, create_commit, create_pull_request |

## SKILL.md Schema (skills/<name>/SKILL.md)
Each skill declares YAML front matter:
  ---
  name: <kebab-case>
  description: <one line, used for routing/recall>
  model: haiku | sonnet | opus
  cache: true            # participates in Module 5 prompt caching
  ---
  <system prompt / reasoning instructions>

## Model Routing (bfsi/model_router.py)
- Haiku  -> cheap, high-volume classification (batch fraud scoring, intent tagging)
- Sonnet -> default reasoning (chatbot, compliance narrative, KYC extraction)
- Opus   -> highest-stakes decisions (final approval, judge evaluation, ambiguous fraud)
Log the routing rationale for every request to audit_log/model_routing.jsonl.

## PCI DSS Constraints (enforced across ALL components)
- Never log full PAN/card numbers; mask to last 4 digits.
- Sanitize all chatbot/user input before it reaches a tool or the model.
- Enforce per-session rate limiting on money-movement operations.
- All money-movement and compliance decisions must be audited (who/what/when).
- Secrets come from environment variables only; never hard-code keys.

## Audit Log Locations
- audit_log/mcp_tool_calls.jsonl   -> every MCP tool call (PreToolUse hook)
- audit_log/model_routing.jsonl    -> model selection rationale per request
- audit_log/transactions.jsonl     -> production transaction audit trail
- audit_log/bandit_scan.txt        -> PostToolUse security scan output

## Compliance Pipeline Order (bfsi/compliance/pipeline.py)
KYC -> AML -> Sanctions -> Approval. A transaction advances only if the prior
stage passes; any BLOCK stops the pipeline and is audited.

## Definition of Done
pytest passes with zero failures; bandit has no medium+ findings; every MCP hop
is audited; Claude-as-Judge scores the platform >= 4 on the compliance rubric.
