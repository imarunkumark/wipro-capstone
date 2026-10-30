# AI Banking Platform — Architecture

Heritage National Bank capstone. This document describes the layered platform
as implemented in `bfsi/`, `skills/`, `.claude/`, and `.github/workflows/`.
`CLAUDE.md` is the authoritative development context; this document is
descriptive and is aligned to the current code.

## Layer overview

Layered integration developed inside Claude Code:

1. Repo instrumentation (CLAUDE.md) — authoritative development context.
2. MCP integration layer — customer-info, banking-api, github servers; every
   hop audited to audit_log/mcp_tool_calls.jsonl.
3. Claude Skills layer — six cached skills as the reasoning library.
4. Chatbot — guardrailed, streaming, fraud tool-use.
5. Fraud + KYC + Compliance pipeline — KYC -> AML -> Sanctions -> Approval.
6. Transaction processing — full audit trail; model routing Haiku/Sonnet/Opus.
7. Batch API fraud pipeline — synthetic transactions scored at the Haiku tier.
8. Hooks, slash commands, sub-agents — governance woven into the dev workflow.
9. CI/CD gate — headless Claude-as-Judge (score >= 4) blocks merge.

```
                 +------------------------------------------------+
  python3 -m     |  bfsi/main.py  (end-to-end workflow + batch)   |
  bfsi.main ---> +------------------------------------------------+
                        |                              |
                        v                              v
          bfsi/transactions.py               bfsi/batch_fraud.py
           (process + audit trail)            (synthetic batch, Haiku tier)
                        |                              |
                        v                              |
          bfsi/compliance/pipeline.py                  |
           KYC -> AML -> SANCTIONS -> APPROVAL         |
             |       |         |                       |
             |       v         v                       |
             |  bfsi/fraud_engine.py <-----------------+
             |       |   bfsi/compliance/sanctions_check.py
             v       v
          bfsi/mcp/registry.py  (in-process MCP router + audit)
             |                         |
             v                         v
   customer_info_server.py     banking_api_server.py      (FastMCP)

  bfsi/model_router.py  -> audit_log/model_routing.jsonl
  bfsi/skills_loader.py -> cached system block from skills/*/SKILL.md
  bfsi/chatbot.py, bfsi/kyc_vision.py, bfsi/judge.py -> Anthropic SDK via OpenRouter
```

## Layer 1 — Repo instrumentation (`CLAUDE.md`)

Defines the MCP registry, SKILL.md schema, model-routing tiers, PCI DSS
constraints, audit log locations, compliance pipeline order, and the
Definition of Done (pytest green, no bandit medium+ findings, every MCP hop
audited, judge score >= 4).

## Layer 2 — MCP integration (`bfsi/mcp/`, `.claude/mcp.json`)

| Component | Responsibility |
|-----------|----------------|
| `customer_info_server.py` | FastMCP server `customer-info`. In-memory demo customers `C5001`, `C5002`. Tools: `get_customer` (master record incl. `kyc_verified`, `home_country`), `check_customer_history` (count + `avg_amount`), `verify_ip_location` (`geo_mismatch` = request country != home country). |
| `banking_api_server.py` | FastMCP server `banking-api`. In-memory accounts `AC5001`, `AC5002`. Tools: `get_balance`, `transfer_funds` (rejects unknown accounts and insufficient funds, otherwise debits/credits), `apply_loan` (demo rule: <= 25000 APPROVED, else REFERRED). |
| `registry.py` | In-process router used by the Python platform. `call(server, tool, **args)` dispatches to the server function, then appends an audit record. Unknown tools raise `KeyError`. |
| `.claude/mcp.json` | Registers the same two servers for Claude Code as stdio processes (`python3 bfsi/mcp/<server>.py`) plus the `github` server (`npx -y @modelcontextprotocol/server-github`, token from `GITHUB_TOKEN`). |

The `github` server (create_branch / create_commit / create_pull_request) is
used only from Claude Code sessions; no platform code calls it.

Two audit paths write to `audit_log/mcp_tool_calls.jsonl`:

- Platform code path (`registry._audit`): `{"seq", "server", "tool", "args", "ok"}`.
  `args` pass through `_mask()`, which masks any string arg whose key contains
  `card` to `****` + last 4. `ok` is false when the result has an `error` key.
  `seq` is a per-process counter.
- Claude Code session path (PreToolUse hook, see Layer 8): `{"tool", "ts"}` for
  every `mcp__.*` tool call.

Within `python3 -m bfsi.main` the servers are imported as modules and called
directly; they are not spawned as separate MCP processes. Account balances are
in-memory and reset on every process start.

## Layer 3 — Claude Skills (`skills/*/SKILL.md`, `bfsi/skills_loader.py`)

Each skill has front matter `name`, `description`, `model`, `cache: true`
followed by a system-prompt body.

| Skill | Declared model | Purpose | Used by code |
|-------|----------------|---------|--------------|
| `customer-support` | sonnet | Guardrailed retail-banking answers | `chatbot.reply` |
| `fraud-triage` | haiku | Return `{"risk","reason"}` JSON from signals | `fraud_engine.score_transaction` |
| `kyc-extraction` | sonnet | Extract identity fields, doc number masked to last 4 | `kyc_vision.extract_identity` |
| `compliance-narrative` | sonnet | Audit-ready narrative from stage results | not called in `bfsi/` |
| `risk-scoring` | haiku | Return `{"tier"}` JSON | not called in `bfsi/` |
| `sanctions-summary` | opus | Summarize a hit, recommend CLEAR/ESCALATE | not called in `bfsi/` |

`skills_loader.py`:
- `load_skills()` parses every `skills/*/SKILL.md` (path is relative to CWD).
- `build_cached_system(active)` concatenates the selected skill bodies into one
  system text block marked `cache_control: {"type": "ephemeral"}` (prompt caching).
- `get_skill(name)` returns one parsed skill or raises `KeyError`.

The `model` front-matter field is documentation only; the loader does not use
it to select a model.

## Layer 4 — Chatbot (`bfsi/chatbot.py`)

- `sanitize(text)`: drops non-printable characters, replaces
  `ignore previous`, `system prompt`, `full card number` (case-insensitive)
  with `[removed]`, truncates to 2000 characters.
- `fraud_tools(customer_id, ip_country)`: calls `check_customer_history` and
  `verify_ip_location` through the audited registry.
- `reply(...)`: sanitizes input, gathers fraud signals, calls `MODEL_SONNET`
  with the cached `customer-support` system block; streams via
  `client.messages.stream` by default, or uses a single `messages.create` call.
  No offline fallback — requires `OPENROUTER_API_KEY`. Not invoked by `main.py`.

## Layer 5 — Fraud + KYC + Compliance pipeline

### Fraud engine — `bfsi/fraud_engine.py`
`score_transaction(customer_id, amount, ip_country)`:
1. MCP `customer-info.check_customer_history` and `customer-info.verify_ip_location`.
2. Signals `{amount, avg_amount, geo_mismatch}` sent to `MODEL_HAIKU` with the
   cached `fraud-triage` skill; JSON parsed from the reply (`engine: "claude"`).
3. On any exception (no key, network, parse error): deterministic fallback —
   `HIGH` if `amount > max(3 * avg_amount, 5000)` or `geo_mismatch`, else
   `LOW` (`engine: "fallback"`, `fallback_reason` recorded).

### KYC vision — `bfsi/kyc_vision.py`
`extract_identity(doc_text)` sends document text to `MODEL_SONNET` with the
`kyc-extraction` skill; on a failed model call it returns `UNKNOWN` fields and a
masked `doc_number`. It is a standalone component; the pipeline's KYC stage
uses the `kyc_verified` flag from `get_customer`, not this function.

### Sanctions — `bfsi/compliance/sanctions_check.py`
Normalized name screened against a demo watchlist (`ivan petrov`,
`acme shell holdings`, `redline logistics`). Exact match -> `STRONG`;
substring either way -> `PARTIAL`; otherwise `NONE`.

### Pipeline — `bfsi/compliance/pipeline.py`
`run_compliance(customer_id, name, amount, ip_country)` runs strictly in order
and returns on the first failure with `{"decision": "BLOCK", "failed_stage", "stages", ...}`:

| Stage | Check | Passes when |
|-------|-------|-------------|
| KYC | MCP `get_customer` | `kyc_verified is True` (unknown customer fails) |
| AML | `score_transaction` | `risk != "HIGH"` |
| SANCTIONS | `sanctions_check(name)` | no hit, or hit with `PARTIAL` strength (only `STRONG` blocks) |
| APPROVAL | — | reached only if all above pass -> `decision: "APPROVE"` |

## Layer 6 — Transaction processing (`bfsi/transactions.py`)

`process(request_id, customer_id, name, from_account, to_account, amount, ip_country="IN")`

### Control/data flow: lookup -> balance -> compliance -> transfer

1. `route("reason", request_id)` — logs the Sonnet-tier rationale to
   `audit_log/model_routing.jsonl`.
2. Customer lookup (KYC): `registry.call("customer-info", "get_customer")` ->
   MCP audit record.
3. AML: `fraud_engine.score_transaction` -> `check_customer_history` and
   `verify_ip_location` (two MCP audit records) -> Haiku model or fallback rule.
4. Sanctions: local watchlist screen (no MCP hop).
5. If decision != APPROVE: result `status: "REJECTED"`, `reason` = failed stage;
   no money moves.
6. If APPROVE: `route("decide", request_id)` logs the Opus-tier rationale, then
   `registry.call("banking-api", "transfer_funds", ...)` (MCP audit record).
   The balance check happens inside `transfer_funds`: unknown account ->
   `account_not_found`, balance < amount -> `insufficient_funds`. Result
   `status` is `SETTLED` if `ok`, otherwise `FAILED`.
7. The full result (status, compliance stages, transfer result) is appended to
   `audit_log/transactions.jsonl`.

`banking-api.get_balance` is available through the registry for standalone
balance lookups, but `process()` does not call it separately; the
authoritative balance validation is in `transfer_funds`.

Demo runs in `bfsi/main.py`:
- `R1001` — `C5001` / Asha Rao, 750.00 from `AC5001`, IP `IN` -> expected `SETTLED`.
- `R1002` — `C5002` / Ivan Petrov, 5000.00 from `AC5002`, IP `RU` -> expected
  `REJECTED` (geo mismatch drives AML to HIGH under the fallback rule;
  `Ivan Petrov` is also a STRONG sanctions hit).

### Model routing — `bfsi/model_router.py`

`route(task, request_id)` returns a model slug and appends
`{"request_id", "task", "model", "rationale"}` to `audit_log/model_routing.jsonl`.
Unknown task classes default to `reason`.

| Task class | Env var | Default slug | Rationale | Callers |
|------------|---------|--------------|-----------|---------|
| `classify` | `MODEL_HAIKU` | `anthropic/claude-3.5-haiku` | high-volume, low-stakes classification | `batch_fraud.run_batch` (per transaction) |
| `reason` | `MODEL_SONNET` | `anthropic/claude-sonnet-4.5` | default reasoning | `transactions.process` (every request) |
| `decide` | `MODEL_OPUS` | `anthropic/claude-opus-4.1` | highest-stakes decisions | `transactions.process` (before transfer), `judge.evaluate` |

`fraud_engine`, `chatbot`, and `kyc_vision` read `MODEL_HAIKU` / `MODEL_SONNET`
directly rather than calling `route()`, so their calls are not separately
logged in `model_routing.jsonl`.

All model calls use the Anthropic SDK with `auth_token=OPENROUTER_API_KEY` and
`base_url=ANTHROPIC_BASE_URL` (default `https://openrouter.ai/api`).

## Layer 7 — Batch fraud pipeline (`bfsi/batch_fraud.py`)

`run_batch()` scores four synthetic transactions (`B1`-`B4`): for each, logs a
`classify` route and calls `score_transaction`. Results
`[{"id","risk","engine"}]` are written to `audit_log/batch_results.json`
(overwritten each run). It emulates the Batch API pattern with sequential
calls; it does not use the Message Batches endpoint.

## Layer 8 — Governance: hooks, slash commands, sub-agents

### Hooks — `.claude/settings.json`
| Hook | Matcher | Action |
|------|---------|--------|
| PreToolUse | `mcp__.*` | Inline Python appends `{"tool", "ts"}` (UTC) to `audit_log/mcp_tool_calls.jsonl` |
| PostToolUse | `Edit\|Write` | `bandit -q -r bfsi -f txt -o audit_log/bandit_scan.txt \|\| true` (non-blocking) |

### Slash commands — `.claude/commands/`
| Command | Arguments | Behaviour |
|---------|-----------|-----------|
| `/add-bfsi-skill` | `<skill-name> <model>` | Scaffold `skills/<name>/SKILL.md` per the CLAUDE.md schema and confirm it loads via `skills_loader.py` |
| `/generate-compliance-report` | — | Read the three JSONL audit logs and write `reports/compliance_report.md` |
| `/security-review` | `<path>` | Review a file against PCI DSS constraints and run `bandit -r <path>` |

Sub-agents are used for delegated work in the Claude Code workflow; no
sub-agent definitions are checked into `.claude/`.

## Layer 9 — CI/CD gate (`.github/workflows/ci_gate.yml`, `bfsi/judge.py`)

Workflow `capstone-ci-gate` runs on pull requests to `main` (ubuntu-latest,
Python 3.11) with `OPENROUTER_API_KEY` from repository secrets and the base URL
and model slugs set in `env`. Steps, each must succeed:

1. `pip install anthropic python-dotenv "mcp<2" bandit pytest`
2. `python -m pytest tests/ -q`
3. `bandit -q -r bfsi -ll` (fails on medium+ findings)
4. `python -m bfsi.judge`

`bfsi/judge.py`:
- Evidence = line counts of `mcp_tool_calls.jsonl`, `transactions.jsonl`,
  `model_routing.jsonl` (0 if missing).
- Routes to the `decide` (Opus) tier; the rubric covers MCP audit
  traceability, compliance pipeline correctness, PCI DSS hardening,
  model-routing rationale, and test coverage; expects `{"score","recommendation"}`.
- Writes `reports/judge_evaluation.md` (score, recommendation, evidence,
  READY / NOT READY) and exits 0 if `score >= 4`, else 1.
- Caveat: on any exception (missing key, network, parse error) it falls back to
  `score: 4` with `fallback_reason`, so the gate passes without a live model
  verdict. Check `fallback_reason` in the output.

## Audit log locations

| File | Writer | Content |
|------|--------|---------|
| `audit_log/mcp_tool_calls.jsonl` | `bfsi/mcp/registry.py`; PreToolUse hook | Every MCP hop (masked args) / every Claude Code `mcp__*` call |
| `audit_log/model_routing.jsonl` | `bfsi/model_router.py` | Task class, model, rationale per routed request |
| `audit_log/transactions.jsonl` | `bfsi/transactions.py` | Full result per transaction (status, stages, transfer) |
| `audit_log/batch_results.json` | `bfsi/batch_fraud.py` | Latest batch scoring results |
| `audit_log/bandit_scan.txt` | PostToolUse hook | Latest bandit scan after edits |
| `reports/judge_evaluation.md` | `bfsi/judge.py` | Latest judge verdict |

All paths are relative to the working directory; run everything from the repo root.

## PCI DSS controls as implemented

| Constraint (CLAUDE.md) | Implementation |
|------------------------|----------------|
| Mask PAN to last 4 | `registry._mask` for args with `card` in the key; `kyc-extraction` skill masks doc numbers |
| Sanitize input | `chatbot.sanitize` |
| Audit money movement and decisions | MCP audit log + `transactions.jsonl` + `model_routing.jsonl` |
| Secrets from env only | All keys read via `os.environ`; `.env` loaded by `python-dotenv` in `main.py` |
| Per-session rate limiting on money movement | Not implemented in the current code |
