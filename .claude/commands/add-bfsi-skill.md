---
description: Scaffold a new BFSI skill (skills/<name>/SKILL.md) with valid front matter
argument-hint: <skill-name> <model:haiku|sonnet|opus>
---
Create a new skill at `skills/$1/SKILL.md` following the SKILL.md schema in
CLAUDE.md: kebab-case name `$1`, a one-line description, model `$2`, cache: true,
and a focused system prompt. Then confirm it loads via bfsi/skills_loader.py.
