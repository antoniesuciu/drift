# GOAL: Implement M1 — Project Foundation

You are the lead quantitative software engineer working on `quant-trading-lab`, a modular algorithmic trading platform supporting rule-based, ML-based, and LLM-based trading agents.

M0 (Research and Architecture) is complete.

The repository already contains professionally structured requirements, architectural decisions, a roadmap, research documentation, and an AGENTS.md.

Your task is to implement **Milestone 1: Project Foundation**.

Work autonomously within the approved scope, implement the required components, run tests, and verify completion against the milestone's acceptance criteria.

## 1. Read the Existing Project Documentation

Before writing code, read:

- `AGENTS.md`
- `REQUIREMENTS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/PROJECT_MEMORY.md`

Read additional documents only when relevant.

The existing documentation is authoritative.

Identify the exact scope, dependencies, and acceptance criteria for M1.

Do not silently redesign the architecture or expand the milestone.

If this prompt conflicts with an accepted architectural decision, preserve the existing decision and report the conflict.

## 2. Inspect the Development Environment

Identify:

- Operating system.
- Installed Python versions.
- Available package managers.
- Existing project configuration.
- Git branch and working-tree status.
- Installed MCP tools and relevant skills.

Use Context7 and official documentation when verifying library compatibility.

Prefer Python tooling already established in the repository. If none has been selected, choose a modern, reproducible setup such as `uv` with `pyproject.toml`.

Document important dependency decisions.

Do not install unnecessary frameworks.

## 3. Initialize the Python Project

Create a clean, installable Python package using a `src` layout.

Preferred package name:

`quantlab`

Configure:

- `pyproject.toml`
- Reproducible dependency resolution.
- Python version requirements.
- pytest.
- Ruff for formatting and linting.
- Type checking where appropriate.
- Minimal package entry points.
- Development commands in README.md.

Use compatible, pinned or appropriately constrained dependency versions.

The project must be straightforward to install and test on a fresh development environment.

Avoid unnecessary abstractions.

## 4. Verify NautilusTrader Compatibility

NautilusTrader is our preferred backtesting and trading engine, but its suitability must be verified.

Using current official documentation:

1. Identify a compatible Python and NautilusTrader version.
2. Install the framework in the project environment.
3. Verify successful imports.
4. Investigate the relevant APIs for historical backtesting and future Interactive Brokers integration.
5. Implement a minimal synthetic-data backtesting smoke test using actual NautilusTrader functionality.
6. Verify that the smoke test runs deterministically.

Use supported framework APIs.

Do not implement a custom trading engine.

Do not connect to Interactive Brokers.

If NautilusTrader has compatibility issues, document them and propose the smallest reasonable resolution rather than silently replacing the framework.

## 5. Establish the Minimal Shared Architecture

Follow `docs/AGENT_ARCHITECTURE.md`.

Prepare a minimal, extensible package structure supporting future:

- Rule-based agents.
- Machine-learning agents.
- LLM research agents.
- Market-data processing.
- Backtesting.
- Portfolio management.
- Risk controls.
- Broker adapters.

Define only the foundational types or interfaces explicitly needed by M1.

All future agent families should be able to produce standardized proposals or signals through a shared contract, consistent with the existing architecture.

However:

**Do not implement speculative abstractions, empty modules, agent orchestration systems, ML training pipelines, or LLM integrations.**

Do not duplicate functionality already provided by NautilusTrader.

Favor a small, working foundation over an elaborate architecture.

## 6. Configure Automated Testing

Use pytest.

Implement tests covering the M1 requirements, including where applicable:

- Package imports.
- Basic configuration validation.
- Shared data structures and contracts.
- Invalid input handling.
- NautilusTrader compatibility.
- Synthetic market-data processing.
- Deterministic backtesting smoke test.

Ensure that all tests run without:

- Broker accounts.
- API credentials.
- Internet access.
- Paid market data.
- External services.

Use small synthetic fixtures.

Synthetic data must be clearly identified as synthetic and never represented as genuine historical market data.

Include negative tests for important validation boundaries.

## 7. Establish Quality Controls

Configure:

- Ruff formatting.
- Ruff linting.
- pytest.
- Type checking if selected.
- Reproducible development commands.

Add a minimal GitLab CI pipeline if appropriate for the existing repository.

CI should validate formatting, linting, and tests without requiring brokerage credentials or paid services.

Avoid introducing Docker unless M1 explicitly requires it.

Ensure `.gitignore` excludes:

- Virtual environments.
- Python caches.
- Credentials.
- Historical datasets.
- Local databases.
- Model checkpoints.
- Generated results.
- Temporary files.

Preserve the existing Git ignore rules unless corrections are necessary.

## 8. Preserve Obsidian Project Memory

The project uses an Obsidian vault for persistent memory.

The dedicated namespace is:

`Memories/Projects/Quant-Trading-Lab/`

Follow the memory-isolation rules from AGENTS.md.

You may read relevant project memory and update this project's `Current State` note after completing M1.

Do not modify other projects' notes.

Do not update shared/global memory files.

If Obsidian MCP is unavailable, use only the explicitly documented, validated local fallback if one exists.

Otherwise, record the proposed memory update in the repository rather than guessing vault paths.

Git remains the authoritative source for implementation and technical documentation.

## 9. Scope Restrictions

Do NOT:

- Implement the ITSM trading strategy yet.
- Implement additional trading strategies.
- Train ML models.
- Implement LLM agents.
- Build a custom backtesting engine.
- Connect to Interactive Brokers.
- Submit paper or real orders.
- Purchase or download paid market data.
- Implement live trading.
- Deploy cloud services.
- Introduce unnecessary databases or services.
- Modify unrelated projects or repositories.

This milestone establishes the technical foundation only.

## 10. Validate M1 Completion

Before declaring completion:

1. Confirm all relevant M1 acceptance criteria from `docs/ROADMAP.md` are satisfied.
2. Run formatting checks.
3. Run linting checks.
4. Run automated tests.
5. Execute the NautilusTrader synthetic-data smoke test.
6. Confirm deterministic behavior.
7. Verify that no broker connection or live-order pathway exists.
8. Review the Git diff.
9. Verify no credentials, large datasets, or generated artifacts are staged.

If something fails, investigate and fix it within M1 scope.

Do not claim completion if required acceptance criteria remain unmet.

## 11. Update Documentation

Update the relevant documentation to reflect the actual implementation.

At minimum:

- README.md — installation, development commands, and testing.
- docs/ROADMAP.md — accurate M1 status.
- docs/PROJECT_MEMORY.md — current implementation state, where appropriate.

Update architecture documentation only when necessary.

Do not rewrite the entire M0 documentation.

Record any material architectural decisions separately.

## 12. Git Commit

You are connected to Git.

After implementation and successful validation:

1. Review Git status and the diff.
2. Stage only files relevant to M1.
3. Verify no secrets or datasets are included.
4. Create one clean local commit.

Suggested commit message:

`feat: establish quant trading platform foundation`

Do not rewrite Git history.

Do not modify remote configuration.

Do not push to GitLab or GitHub.

If acceptance criteria remain unmet, report the blockers instead of committing an incomplete milestone as complete.

## 13. Final Report

Provide a concise technical summary containing:

1. Implemented components.
2. Final package structure.
3. Python and NautilusTrader versions.
4. Important architectural decisions.
5. Tests executed and their results.
6. NautilusTrader compatibility findings.
7. Any remaining limitations.
8. Obsidian memory updates.
9. Git commit hash.
10. Recommended next task for M2.

Avoid unnecessary explanations.

**Success condition:** We have a working, reproducible, tested Python foundation using NautilusTrader, ready for historical market-data integration and development of our first rule-based trading agent.

Do not begin M2 automatically.
