# Project memory (Obsidian)

The repository is authoritative for specifications and protocols. Obsidian holds concise navigation, durable decisions and unfinished work.

## Location

Notes live in `Memories/Projects/Quant-Trading-Lab/`: `Project Overview.md` (entry point), `Current State.md`, `Architecture Decisions.md`, `Research Summary.md`, `Real Data Preparation.md`. Codex and Claude Code share these notes; start at the overview, then Current State. There are no agent-specific folders or tags. InvestorAI has its own sibling namespace and is not part of this memory.

## Tools

Prefer the Obsidian MCP tools and verify their availability each session; use move operations to relocate notes so links survive. Direct filesystem access is a fallback only after verifying the vault path and permission. If neither route works, report the limitation. Never write to another project's notes, global memory or vault configuration.

## Maintenance

- Read a note before updating it, search project memory before substantial work, and reverify older claims against the repository.
- Keep updates small and reusable: decisions with rationale, validated findings, blockers, milestone state. Link to repository documents; do not copy reports or completion logs.
- Distinguish recorded validation from checks rerun in the current task, and record commit IDs only after they exist.
- Never store credentials, account identifiers or personal financial details.
