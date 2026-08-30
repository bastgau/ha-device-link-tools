# CLAUDE.md — HA Device Link Tools

Home Assistant custom integration that links existing entities to an existing device,
for entities whose own integration offers no device option. It creates no entities: it
registers three actions, an options flow and a repairs flow.

## Language

Reply to the user in **French**. Everything that lands in the repository is in
**English**: code, comments, docstrings, error messages, `strings.json`, commit
messages, README.

## Commands

```bash
scripts/lint [integration|tests|repo|all]   # ruff check, ruff format, pylint, pyright, docstring-linter
scripts/test                                # pytest with coverage
scripts/develop                             # run Home Assistant against ./config
```

CI runs the same five checks over two scopes (`custom_components/device_link_tools/*.py`
and `tests`). `scripts/lint` predicts CI: run it before saying work is done. Coverage
must stay above 95% (`--cov-fail-under=95`).

See **[scripts/README.md](scripts/README.md)** for every script, its scopes and its side
effects — notably that `scripts/lint repo` reformats files in place, and that
`scripts/update_requirements` has to be re-run whenever `homeassistant` is upgraded.

## Commits

`.commitlintrc.mjs` enforces, and the rules are stricter than usual:

- types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- subject lowercase, 15–100 chars, no trailing period
- **body and footer must be empty** — title only, no description, no `Co-Authored-By`

Pre-commit blocks commits to `main`/`master`, but **not** to `develop`, which is the
default branch: create a branch yourself rather than committing to `develop` directly.

## Design rules that are not obvious from the code

These were deliberate and cost real debugging. Do not undo them casually.

- **One write path.** `async_apply_link` in `reapply.py` is the only place a device link
  is written. Actions, options flow and repairs flow all go through it, so refusals, the
  registry write and the recorded table cannot drift apart. Do not write
  `async_update_entity(device_id=...)` anywhere else.
- **Never write a link that cannot be recorded.** A link this integration does not
  remember is one it can no longer undo: it is lost at the next restart, and refused as
  `link_set_elsewhere` in the meantime. Hence the `entry_not_loaded` guard _before_ any
  registry write, and the `finally` that records whatever was already written when a
  later entity fails.
- **Refuse rather than write something that will not survive a restart.** Same bargain
  for a device with no identifiers, a composite device id, and a child device (the entity
  registry accepts a child, but `async_get_devices` searches main devices only, so the
  link could never be resolved again). Prefer a clear refusal over a silent loss.
- **Only touch links this integration recorded.** A link an entity's own integration
  declares is written back on every restart, so it must be changed at the source — even
  re-asserting the same device is refused, because coincidence is not tracking.
- **Re-application only fills an empty link**, never overwrites one the owning
  integration set.

## Error messages

Every failure raises `ServiceValidationError`/`HomeAssistantError` with a
`translation_key`, never a bare string. Each key needs an entry in **both**
`strings.json` and `translations/en.json` (keep the two files identical and the keys
alphabetically sorted), and, if the options flow can hit it, in `_FORM_ERRORS` in
`config_flow.py` — otherwise the form falls back to a generic "invalid device".

Messages say _why_ and _what to do next_. Match that tone.

## Working expectations

- **Verify, don't assume.** This integration writes to Home Assistant's internal
  registries, whose behaviour is easy to guess wrong. Read the installed
  `homeassistant` source, or write a throwaway test, before asserting how a registry
  behaves — several review findings turned out to be wrong that way, and one real bug
  was only found by running the code.
- **A guard test must be able to fail.** After writing a regression test, reintroduce the
  bug once and check the test actually goes red.
- **Deprecations are dated.** Home Assistant reports a custom integration's use of a
  deprecated API through the `homeassistant.helpers.frame` logger, naming the release it
  breaks in. `tests/test_composite_device.py` asserts no such warning is emitted; keep it
  passing rather than silencing it.
- Delete throwaway probe files before finishing, and report failures plainly.
