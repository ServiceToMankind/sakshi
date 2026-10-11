<!--
  Thank you for contributing to Sakshi.
  Please keep it calm and precise, and fill in every section.
-->

## Summary

<!-- What does this PR change, and why? Link the issue it closes. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Documentation
- [ ] Tooling / CI
- [ ] Schema change (needs extra care, see the checklist)

## Checklist

- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat:`, `fix:`, `docs:`).
- [ ] `make check` passes locally (ruff, mypy `--strict`, pytest, schema validation, `pii_guard`, the readability, secret and count checks, eslint, prettier).
- [ ] Tests are added or updated; pipeline coverage stays at 85% or more, and `sanitize.py` / `pii_guard.py` stay at 100%.
- [ ] `mypy --strict` is clean, and any new Python is fully typed.
- [ ] `pii_guard` passes: no forbidden field names and no personal-data-shaped values reach disk.
- [ ] Nothing under `data/` was edited by hand. Only the pipeline writes `data/`.
- [ ] `additionalProperties: false` is still in place at every level of every schema.
- [ ] The protected files (`sanitize.py`, `pii_guard.py`, the forbidden-field list, and the schemas) are unchanged, or a human-approved issue allowing the change is linked below.
- [ ] Nothing that could identify a victim appears anywhere in the diff, including tests and fixtures (fixtures use `TESTVILLE` and obviously fake values).
- [ ] No commit has a `Co-Authored-By: Claude` or other AI co-author line (org policy).
- [ ] Docs are updated if behaviour, a schema, or the way contributors work has changed.

## Approval for changing a protected file

<!--
  Only if this PR touches sanitize.py, pii_guard.py, the forbidden-field list,
  or a schema. Otherwise write "N/A".
-->

Approving issue: #

## Notes for reviewers

<!-- Anything reviewers should look at closely, trade-offs, or follow-ups. -->
