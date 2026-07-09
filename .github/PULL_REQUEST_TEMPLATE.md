<!--
  Thank you for contributing to Sakshi.
  Keep the tone restrained and precise. Fill in every section.
-->

## Summary

<!-- What does this PR change, and why? Link the issue it resolves. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Documentation
- [ ] Tooling / CI
- [ ] Schema change (requires extra scrutiny — see checklist)

## Checklist

- [ ] PR title follows [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat:`, `fix:`, `docs:`).
- [ ] `make check` passes locally (ruff + mypy `--strict` + pytest + schema validation + eslint + prettier).
- [ ] Tests added or updated; pipeline coverage stays >= 85% and `sanitize.py` / `pii_guard.py` stay at 100%.
- [ ] `mypy --strict` is clean; new Python is fully typed.
- [ ] `pii_guard` is green — no forbidden field names and no PII-shaped values reach disk.
- [ ] No hand-edited files under `data/`. The `data/` tree is only ever produced by the pipeline.
- [ ] `additionalProperties: false` remains at every object level in every schema (not loosened).
- [ ] Guardrail files (`sanitize.py`, `pii_guard.py`, the forbidden-field list, and the schemas) are unchanged — or, if changed, a human-approved issue authorizing it is linked below.
- [ ] No victim-identifying information appears anywhere in the diff, including tests and fixtures (fixtures use `TESTVILLE` and obviously-synthetic values).
- [ ] Commits contain **no** `Co-Authored-By: Claude` / AI co-author trailer (org policy).
- [ ] Docs updated if behavior, schema, or contributor workflow changed.

## Guardrail-change authorization

<!--
  Only if this PR touches sanitize.py, pii_guard.py, the forbidden-field list,
  or a schema. Otherwise write "N/A".
-->

Authorizing issue: #

## Notes for reviewers

<!-- Anything reviewers should focus on, trade-offs, or follow-ups. -->
