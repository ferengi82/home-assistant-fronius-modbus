# AGENTS.md

> 🤖 This repository was generated and is maintained with **AI (Anthropic Claude Code)**.

This file exists so AI coding tools that look for `AGENTS.md` (e.g. OpenAI Codex, Cursor, others) find the project guidance.

**The full agent/developer guide lives in [CLAUDE.md](CLAUDE.md)** — architecture, repository layout, how SunSpec discovery/decoding works, conventions, build/test/verify commands, the release/deploy workflow, and gotchas. Please read it before making changes.

Quick reference:

- Integration: Home Assistant custom component `fronius_symo_modbus`, reads a Fronius Symo Advanced over Modbus TCP (SunSpec). Read-only.
- Register map details: [docs/SUNSPEC.md](docs/SUNSPEC.md).
- Tests: `python -m pytest tests -q` (no Home Assistant needed; `sunspec.py` is a pure module).
- CI must stay green: hassfest + HACS + pytest (`.github/workflows/validate.yml`).
- Ship via feature branch → PR → squash-merge → tagged GitHub release (HACS only updates on releases).
- Do **not** rename the domain back to `fronius_modbus` (collides with `redpomodoro/fronius_modbus`).
