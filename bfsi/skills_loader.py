"""Consolidate the six skills into a cached system block.

Module 5 prompt caching: the concatenated skill library is a large, stable
context, so mark it with cache_control so it is billed once and reused across
calls. Returns Anthropic-style system blocks ready to pass to messages.create.
"""
from pathlib import Path

SKILLS_DIR = Path("skills")


def load_skills() -> list[dict]:
    """Return each skill's parsed front matter + body."""
    skills = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text()
        _, fm, body = text.split("---", 2)
        meta = {}
        for line in fm.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        skills.append({"meta": meta, "body": body.strip()})
    return skills


def build_cached_system(active: list[str] | None = None) -> list[dict]:
    """Build a cached system prompt from the (optionally filtered) skill library."""
    skills = load_skills()
    if active:
        skills = [s for s in skills if s["meta"]["name"] in active]
    library = "\n\n".join(
        f"## Skill: {s['meta']['name']}\n{s['body']}" for s in skills)
    return [
        {"type": "text", "text": "Heritage National Bank skill library.\n\n" + library,
         "cache_control": {"type": "ephemeral"}},   # <-- prompt caching
    ]


def get_skill(name: str) -> dict:
    for s in load_skills():
        if s["meta"]["name"] == name:
            return s
    raise KeyError(name)
