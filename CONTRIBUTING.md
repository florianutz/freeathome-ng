# Contributing to free@home NG

Contributions are welcome!

## Development Setup

1. Clone this repository and create a Python 3.12+ virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
2. Run linting, tests, and bytecode verification:
   ```bash
   ruff check custom_components tests
   pytest
   python3 -m compileall -q custom_components/freeathome_ng tests
   ```

## Architecture Guidelines

- Keep the API client and device model layer (`custom_components/freeathome_ng/api/`) free of `homeassistant` imports so it remains independently testable.
- Never reuse the legacy `freeathome` domain, event names, services, or device registry identifiers—everything in this integration must stay isolated under `freeathome_ng`.
- Keep `strings.json`, `services.yaml`, and all 7 `translations/*.json` files in sync (`en`, `de`, `nl`, `fr`, `it`, `es`, `pl`).
- Add unit tests in `tests/` for any new `functionID`, `pairingID`, config flow step, or API endpoint support.
- See [AGENTS.md](AGENTS.md) and [HA Integration Engineering Standards](docs/HA_INTEGRATION_STANDARDS.md) for the complete architecture, compatibility, and quality gates.
