# Deployment Guide

Summary:

- Python 3.10+; `pip install anthropic python-dotenv "mcp<2" bandit pytest`.
- Secrets via environment (.env): OPENROUTER_API_KEY, GITHUB_TOKEN, model slugs.
- Register MCP servers via .claude/mcp.json; validate with the Phase 2 trace.
- Enable hooks in .claude/settings.json (PreToolUse audit, PostToolUse bandit).
- Gate merges on .github/workflows/ci_gate.yml: pytest, bandit, Claude-as-Judge.
- Audit logs under audit_log/ are the compliance system of record.

All commands below run from the repository root. Code paths such as
`audit_log/`, `skills/`, and `reports/` are relative to the working directory.

## 1. Prerequisites

- Python 3.10 or newer. The code uses `list[str] | None` annotations and the
  dict `|` operator. CI uses 3.11.
- Node.js / `npx`, needed only for the `github` MCP server in Claude Code.
- Claude Code, for MCP registration, hooks, and slash commands.

## 2. Virtual environment and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic python-dotenv "mcp<2" bandit pytest
```

`mcp` must be pinned below 2: `bfsi/mcp/customer_info_server.py` and
`bfsi/mcp/banking_api_server.py` import `mcp.server.fastmcp.FastMCP`, which
was removed in mcp 2.x. Because `bfsi/mcp/registry.py` imports both servers,
an unpinned `mcp` breaks the whole platform and the test suite.

## 3. Environment variables (`.env`)

`bfsi/main.py` calls `load_dotenv()`, which reads a `.env` file in the
repository root. Put secrets there or in the shell environment, never in code.
Never commit `.env`.

| Variable | Used by | Required |
|----------|---------|----------|
| `OPENROUTER_API_KEY` | `fraud_engine`, `chatbot`, `kyc_vision`, `judge` (passed as `auth_token`) | Required for live model calls. Without it, fraud scoring and the judge fall back to rules; `chatbot.reply` and `kyc_vision.extract_identity` raise `KeyError`. |
| `ANTHROPIC_BASE_URL` | Same modules | Optional. Defaults to `https://openrouter.ai/api`. |
| `MODEL_HAIKU` | `model_router` (`classify`), `fraud_engine` | Optional. Defaults to `anthropic/claude-3.5-haiku`. |
| `MODEL_SONNET` | `model_router` (`reason`), `chatbot`, `kyc_vision` | Optional. Defaults to `anthropic/claude-sonnet-4.5`. |
| `MODEL_OPUS` | `model_router` (`decide`), `judge` | Optional. Defaults to `anthropic/claude-opus-4.1`. |
| `GITHUB_TOKEN` | `.claude/mcp.json`, mapped to `GITHUB_PERSONAL_ACCESS_TOKEN` for the `github` server | Required only for the GitHub MCP server. |

Only `bfsi/main.py` loads `.env`. When you run `python3 -m bfsi.judge` or
pytest, export the variables in your shell first, for example with
`set -a; . ./.env; set +a`.

## 4. MCP server registration

`.claude/mcp.json` registers three servers for Claude Code:

| Server | Launch |
|--------|--------|
| `customer-info` | `python3 bfsi/mcp/customer_info_server.py` (stdio) |
| `banking-api` | `python3 bfsi/mcp/banking_api_server.py` (stdio) |
| `github` | `npx -y @modelcontextprotocol/server-github`, token from `GITHUB_TOKEN` |

Start Claude Code from the repository root with the venv active, so `python3`
resolves to the interpreter that has `mcp<2` installed. Check that the servers
connect (for example with `/mcp` in Claude Code). Then validate the trace:
call one tool per server and confirm that `audit_log/mcp_tool_calls.jsonl`
gains entries.

The Python platform does not need these processes. `bfsi/mcp/registry.py`
imports the server modules and calls them in-process, auditing each hop.

## 5. Hooks

Hooks are defined in `.claude/settings.json` and apply automatically when
Claude Code runs in this project:

- PreToolUse, matcher `mcp__.*`: appends `{"tool", "ts"}` to
  `audit_log/mcp_tool_calls.jsonl` for every MCP tool call.
- PostToolUse, matcher `Edit|Write`: runs `bandit -q -r bfsi` and writes the
  output to `audit_log/bandit_scan.txt`. This hook does not block (`|| true`).
  `bandit` must be on `PATH`, so keep the venv active.

## 6. Run the platform

```bash
python3 -m bfsi.main
```

This runs two transactions through `transactions.process`:

- `R1001`, expected SETTLED.
- `R1002`, expected REJECTED with the failed stage.

It then runs the four-transaction batch fraud pipeline. Outputs are appended
to, or overwrite, these files:

- `audit_log/transactions.jsonl`
- `audit_log/mcp_tool_calls.jsonl`
- `audit_log/model_routing.jsonl`
- `audit_log/batch_results.json`

Without an API key, fraud scoring uses the deterministic fallback rule. Those
results show `engine: "fallback"`.

## 7. Tests and security scan

```bash
python3 -m pytest tests/ -q
bandit -q -r bfsi -ll
```

- `tests/test_platform.py` covers:
  - MCP hop auditing
  - the approve and sanctions-block paths
  - sanctions strength
  - input sanitization
  - the insufficient-funds edge case
  - transaction audit trail writing

  The tests write to the real `audit_log/` files.
- `bandit -ll` reports only medium and high severity findings. The Definition
  of Done requires zero such findings.

## 8. Claude-as-Judge

```bash
python3 -m bfsi.judge
```

The judge counts the lines in the three JSONL audit logs as evidence. It
routes to the Opus tier and scores the platform from 1 to 5 against the
compliance rubric. It writes `reports/judge_evaluation.md` and prints
`judge score = N -> PASS|FAIL`.

The exit code is 0 only when `score >= 4`. Run `python3 -m bfsi.main` and the
tests first, so the audit logs contain evidence.

If the model call fails for any reason (missing key, network, unparsable
reply), the judge falls back to `score: 4` and records a `fallback_reason`. A
PASS therefore does not prove that a live evaluation ran. Check the output for
`fallback_reason`.

## 9. CI gate (`.github/workflows/ci_gate.yml`)

The `capstone-ci-gate` workflow runs on every pull request to `main`:

1. Check out the code, set up Python 3.11, then run
   `pip install anthropic python-dotenv "mcp<2" bandit pytest`.
2. `python -m pytest tests/ -q`
3. `bandit -q -r bfsi -ll`
4. `python -m bfsi.judge`. The step fails unless the score is >= 4.

Configuration:

- Add the repository secret `OPENROUTER_API_KEY`.
- The workflow sets `ANTHROPIC_BASE_URL`, `MODEL_HAIKU`, `MODEL_SONNET`, and
  `MODEL_OPUS` inline.
- To block merges, make the `gate` job a required status check on `main`.

## 10. Audit logs and reports

| Path | Contents |
|------|----------|
| `audit_log/mcp_tool_calls.jsonl` | MCP hops, from the registry and the PreToolUse hook |
| `audit_log/model_routing.jsonl` | Model routing rationale for each routed request |
| `audit_log/transactions.jsonl` | Transaction audit trail |
| `audit_log/batch_results.json` | Latest batch fraud results |
| `audit_log/bandit_scan.txt` | Latest bandit output from the PostToolUse hook |
| `reports/judge_evaluation.md` | Latest judge verdict |
| `reports/compliance_report.md` | Written by the `/generate-compliance-report` slash command |

Treat `audit_log/` as the compliance system of record: retain it, and do not
edit it by hand.

## Slash commands available in Claude Code

- `/add-bfsi-skill <name> <haiku|sonnet|opus>` scaffolds a new skill.
- `/generate-compliance-report` writes a compliance report from the audit logs.
- `/security-review <path>` runs a PCI DSS and bandit review of a file.
