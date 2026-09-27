# AGENTS.md — dcc-mcp-godot

> Navigation map, not a reference manual. Follow the links; don't read
> everything upfront.

dcc-mcp-godot is the Godot Engine adapter and 2D game-authoring skill set
for the DCC Model Context Protocol (MCP) ecosystem, exposing Godot project,
node and asset operations as typed MCP tools on top of `dcc-mcp-core`.

---

## Repository Contract

**This repository has no justfile. Use `uv` with the `dev` extra, matching CI.**

| Task | Command |
|------|---------|
| Install with dev extras | `uv sync --extra dev` |
| Test | `uv run python -m pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Main-thread budget contract | `uv run pytest -q tests/test_main_thread_budget_contract.py` |

**Repository layout**

| Path | Role |
|------|------|
| `src/dcc_mcp_godot/` | Adapter package — server, dispatcher, skills |
| `docs/` | Documentation |
| `tests/` | pytest suite |
| `tools/` | Dev helper scripts |
| `uv.lock` | Locked dependency set |
| `pyproject.toml` | Package metadata; `dev` extra holds build/pytest/ruff/twine |

**Release flow** — `release-please` on `main` drives `CHANGELOG.md` and the version in
`pyproject.toml` from Conventional Commit subjects. Tagging and
publishing run in CI. Never edit `CHANGELOG.md` or a version string by hand.

**Prohibitions**

- Do not edit `CHANGELOG.md` or version strings manually.
- Do not add a second agent contract file at the repository root; `AGENTS.md` is the single source.
- Do not add a runtime dependency for something only tests need — put it in the `dev` extra.
- Prefer typed skill tools over raw in-Godot scripting.

---

## Agent Contract Files

`AGENTS.md` is the **only** agent contract file at the repository root. It is the
native instruction file for Codex, OpenCode, Cursor, GitHub Copilot, Windsurf,
Cline, Roo Code, Kiro, Trae, and Augment, and Claude Code falls back to it when
no `CLAUDE.md` exists — so do not add `CLAUDE.md`, `GEMINI.md`, `CURSOR.md`, or
any other vendor-specific variant.

**Gemini CLI exception:** Gemini CLI defaults its context file to `GEMINI.md`. To
make it read `AGENTS.md`, set `context.fileName` once in `~/.gemini/settings.json`:

```json
{
  "context": {
    "fileName": ["AGENTS.md", "GEMINI.md"]
  }
}
```
