---
name: check-quality
description: Run the full local quality gate for freeathome_ng (ruff, format, mypy, pytest with coverage incl. migration/coexistence guard suites, translation parity) and summarise failures. Use before finishing any change.
---

# /check-quality

Run every step even if an earlier one fails, then report. Do not fix anything unless the user asks; this skill reports.

## Steps

Run from the repository root:

1. `ruff check custom_components tests scripts`
2. `ruff format --check custom_components tests scripts`
3. `mypy` (configuration in `pyproject.toml`)
4. `pytest --cov --cov-report=term -q`
5. `pytest -q tests/test_migration.py tests/test_coexistence.py` (guard suites; report them separately even if step 4 already ran them)
6. `python3 scripts/check_translations.py`
7. JSON/YAML sanity: `python3 -c "import json,yaml,pathlib as p; d=p.Path('custom_components/freeathome_ng'); [json.loads(f.read_text()) for f in [d/'manifest.json',d/'strings.json',*d.glob('translations/*.json'),*d.glob('icons.json')]]; yaml.safe_load((d/'services.yaml').read_text()); yaml.safe_load((d/'quality_scale.yaml').read_text())"`
8. Optional, only if Docker is available: `docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest`

If a tool is missing, install the pinned stack once with `pip install -r requirements_test.txt` (Python 3.14).

## Report

Reply with one table, then details only for failures:

| Check | Result | Notes |
|---|---|---|
| ruff check | ✅ / ❌ n findings | |
| ruff format | ✅ / ❌ n files | |
| mypy | ✅ / ❌ n errors | |
| pytest | ✅ n passed / ❌ n failed | coverage xx % |
| guard suites | ✅ / ❌ | test_migration, test_coexistence |
| translations | ✅ / ❌ | missing/orphaned/placeholder counts |
| JSON/YAML | ✅ / ❌ | |

For each failure: file:line, the error in one line, and the likely fix. A failing guard suite is always reported first and blocks the change (AGENTS.md section 5).

Untranslated-value warnings from `check_translations.py` are informational; list them only if the change touched translations.
