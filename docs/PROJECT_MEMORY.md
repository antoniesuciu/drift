# Isolated project memory

The Git repository is authoritative for specifications and research protocols. Obsidian holds concise navigation, durable decisions and unfinished work; original research and detailed implementation documentation stay here.

## Location and tools

Read-only discovery found no exposed Obsidian MCP tool or resource in this session. The local Obsidian vault registry identifies `LLMMemory`; its established project convention is `Memories/Projects/`. No existing Quant Trading Lab notes were found. The dedicated namespace is therefore:

```text
Memories/Projects/Quant-Trading-Lab/
├── Project Overview.md
├── Architecture Decisions.md
├── Research Summary.md
├── Current State.md
└── Real Data Preparation.md
```

The local filesystem is a fallback to unavailable MCP, not an installation or reconfiguration of an MCP server. Writes to this external vault require the execution environment's filesystem approval. Prepare and review the exact notes first; create them exclusively inside this namespace. If access is unavailable or denied, leave these as the proposed structure, report the memory deliverable incomplete, and never redirect trading context into another project's notes.

## Contents and maintenance

- Overview: purpose, three agent families, repository document pointers and namespace rule.
- Architecture decisions: adopted stack, provisional Nautilus compatibility, IBKR-first data, shared risk and authorization boundaries.
- Research summary: ITSM adaptation, absence of demonstrated edge, causal timing/cost/data limitations and repository evidence links.
- Current state: M0/M1/M2a/M2b.1 evidence, implemented offline pipeline and verified limitations, M2b.2 preparation with admission pending, later gates, published-history limitation and unresolved account/data inputs. Update actual commit IDs only after they exist.
- Real-data preparation: concise M2b.2 quote/rights/calendar findings, admission prerequisites and links to the repository acquisition plan; keep detailed source research and request tables in Git. Link this topic from the project overview.

Read any existing target note before updating. Search project-specific memory before substantial tasks and reverify older factual claims. Keep updates small and independently reusable; avoid copying full reports or every completion message. Never store credentials, account identifiers, personal financial details or other sensitive information. Do not edit other projects, shared/global memory, vault configuration or folder organization.

## Initialization evidence

Four notes were created locally in the namespace above after the required external-filesystem approval. Their exact contents were read back and verified. All five pre-existing Markdown notes retained their original SHA-256 hashes; no other-project/global note or vault configuration was written. See [INITIALIZATION.md](INITIALIZATION.md). No Obsidian MCP operation is claimed.

## M1 state

The [foundation evidence](M1_FOUNDATION.md) is authoritative for the implemented package and validation. Only this project's `Current State.md` was updated for M1, using the documented local fallback after reading the existing note and snapshotting other Markdown note hashes. At M1 signoff, M2 remained pending and no broker or historical-data work had been performed. Other-project notes, shared/global memory and vault configuration are outside the write scope.

## M2a state

The [MES dataset specification](data/HISTORICAL_DATA_SPEC.md), [provider comparison](data/PROVIDER_COMPARISON.md) and [M2b design](data/INGESTION_DESIGN.md) are authoritative. Update only this project's existing Current State note with the conditional provider recommendation, fixed periods/time/roll policy, unresolved procurement gates and M2b pending. Read the note first and compare all other Markdown hashes after the isolated update. No vendor data, account/license records or full research reports belong in memory.

## M2b.1 state

The [offline implementation report](data/M2B1_IMPLEMENTATION.md) owns actual commands, formats and acceptance mapping. Update only Current State after verification with native synthetic DBN/Parquet/replay results, tests, memory/storage bounds and real-data gates still pending. Hash all other Markdown notes before/after the isolated update. Never treat the fixture calendar, local ingestion receipt or modeled delay as verified vendor coverage, real receipt time, licensing or financial performance.

## M2b.2 preparation state

The [acquisition plan](data/M2B2_ACQUISITION_PLAN.md) and linked vendor/market verification own the detailed evidence. Update Current State and keep independently reusable procurement/calendar findings in the project-specific Real Data Preparation note, linked from Project Overview. All writes remain inside this project's namespace; compare other-note hashes around the isolated update. Public research/planning is prepared, while account-specific quote/rights review, real admission, acquisition and gates 013/014 remain pending. Never store credentials, account-specific records or confidential license text in memory.

## Candlestick requirements plan

The [candlestick specification](CANDLESTICK_AGENTS.md), requirements and roadmap own the detailed catalogue, causal contracts and acceptance gates. Record the durable M3a-then-M3b decision in Architecture Decisions and Current State, with a concise overview pointer. Reuse existing project notes rather than copying the specification into memory. This is planning only: current M2 scope and gates remain unchanged, M3 has not started, and other projects/global notes remain outside the update.

## NVDA scope alignment, 2026-10-30

The user confirmed NVDA ordinary shares, Alpaca historical SIP and IBKR execution; crypto is deferred. [D-026–028](DECISIONS.md), [NVDA_DATA_PLAN.md](data/NVDA_DATA_PLAN.md) and the updated requirements/architecture/roadmap now own that direction. Record the durable source/broker separation, metadata-driven extension interfaces and preserved 2020–2022 / 2023 / 2024–2025 split in the existing project notes. Keep old MES procurement/calendar findings explicitly historical, preserve synthetic runtime evidence, and state that all NVDA admission/strategy gates remain pending. The user subsequently authorized a local commit of these reviewed documents. Implementation, acquisition, orders and push remain outside this task.
