# Research provenance

Source archive: `quant_trading_work_handoff_v2.zip`, supplied 2026-10-29. It contained 14 files: six draft design/specification documents, three handoff/instruction documents, two checksum manifests and three original Gemini reports. All materials were reviewed before final documentation was written. Archived prompts are historical input; the user's current task governs scope and authorizes the final local commit.

Archive SHA-256: `ef212389970ebe6216e7ffe021b07a770cd46c4646b68b7ffa1583a9a3466466`.

## Preserved originals

| File | Bytes | SHA-256 |
|---|---:|---|
| [Broad feasibility](original/gemini_01_broad_feasibility.txt) | 77,890 | `c127dc8b57371b02659401d6dcb35537b9cf1d5a23d99ab3b524769333dbd6a0` |
| [Horizon/strategy comparison](original/gemini_02_horizons_strategy_comparison.txt) | 55,917 | `f1d4ec8f401d32937f89118652a9ee82e0f6b19c6d3bfdbc24cab98800fd7ade` |
| [Empirical short horizon](original/gemini_03_empirical_short_horizon.txt) | 65,150 | `85e19af4dcd8560b7d8da97026e120a822bddeabf3bd26acaa1ee67db2ca83be` |

[SHA256SUMS.txt](original/SHA256SUMS.txt) is also preserved unchanged. Verify from the repository root:

```sh
cd docs/research/original
sha256sum -c SHA256SUMS.txt
```

The extracted package manifest and the original-report manifest both matched before cleanup. These hashes prove preservation relative to the supplied archive, not the reports' factual accuracy or external authenticity. Do not edit the originals to correct their claims; use [RESEARCH_SYNTHESIS.md](../RESEARCH_SYNTHESIS.md).

## Consolidation map

| Supplied material | Final authoritative location |
|---|---|
| `REQUIREMENTS.md` | [Requirements](../../REQUIREMENTS.md), rewritten with measurable staged criteria |
| `docs/AGENT_ARCHITECTURE.md` | [Agent contract](../AGENT_ARCHITECTURE.md) and [platform architecture](../ARCHITECTURE.md) |
| `docs/DECISIONS.md` | [Decision log](../DECISIONS.md), including actual hosting/history evidence |
| `docs/ROADMAP.md` | [Roadmap](../ROADMAP.md), using final user-requested numbering and all milestone fields |
| `docs/RESEARCH_SYNTHESIS.md` | [Synthesis](../RESEARCH_SYNTHESIS.md), reviewed against originals and primary sources |
| `docs/COSTS_AND_PROVIDERS.md` | [Costs/providers](../COSTS_AND_PROVIDERS.md), compatibility and coverage gates |
| `README_HANDOFF.md`, `CODEX_SETUP_PROMPT.md`, `WORK_INSTRUCTIONS.md` | Reconciled into repository README, requirements, AGENTS, roadmap and EXP-001; temporary workflow prompts removed |
| Package checksum manifest | Verified during extraction; report manifest retained; package hashes recorded in this provenance note where independently useful |

The pre-existing `firstResearch.md` (11,921 bytes, SHA-256 `b21bb4ac83f32acd3e440e436348c14e3568a6251a46bd60e3ce7fe5086f1d98`) was a condensed editorial derivative, **not** a byte-identical original. Its useful content is reconciled: spread double-counting and minimum contract sizing in costs/EXP-001; ambiguous intrabar execution and optional CPCV in synthesis; paper/live limitations and recovery in architecture/requirements. Its older market/strategy sequencing yields to current user decisions. Removing it avoids competing specifications; no fourth original report was discarded. Its exact earlier bytes also remain in the preserved published commit.

Temporary archive/extraction material and `INIT_TASK.md` are removed after reconciliation. Published Git history is intentionally retained, so the old archive remains reachable in historical commits even though the final project tree is clean.
