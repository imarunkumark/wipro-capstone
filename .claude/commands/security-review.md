---
description: Run a security review over a target file (PCI DSS + bandit)
argument-hint: <path-to-file>
---
Review `$1` against the PCI DSS constraints in CLAUDE.md: secrets from env only,
PAN masking, input sanitization, rate limiting, and audited money movement.
Run `bandit -r $1` and summarize medium+ findings with concrete fixes.
