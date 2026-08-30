# Development scripts

Every script resolves the repository root from its own location, so it can be run from
anywhere and the repo does not have to sit at `/workspaces/<project>`.

| Script                | What it does                             | Modifies files                                                 |
| --------------------- | ---------------------------------------- | -------------------------------------------------------------- |
| `setup`               | Installs the dev environment             | yes — `./.venv`, and outside the repo (`~/.vimrc`, global npm) |
| `lint`                | Runs the five CI checks, plus Prettier   | yes — the `repo` scope reformats in place                      |
| `test`                | Runs pytest with coverage                | no                                                             |
| `develop`             | Starts Home Assistant against `./config` | yes — `./config` (gitignored)                                  |
| `update_requirements` | Regenerates the `default-config` group   | yes — `pyproject.toml`, `.github/dependabot.yml`, `uv.lock`    |

## `scripts/setup`

Installs everything needed to work on the integration:

- `uv sync --group default-config`, which builds `./.venv` from `uv.lock` — downloading
  the interpreter named in `.python-version` if it is not already there — including the
  `default-config` group that `scripts/develop` needs. That group is **not** a default
  one, so a bare `uv sync` prunes it; run `scripts/setup` again afterwards, or
  `scripts/develop` will fail to boot on a missing `av`/`numpy`;
- Prettier **globally via npm**, pinned to the same version as
  `.pre-commit-config.yaml`, so the hook and `scripts/lint` can never format a file
  differently. Skipped if npm is missing — `scripts/lint` then falls back to `npx`, and
  the pre-commit hook is unaffected;
- a `~/.vimrc` with Python-friendly defaults, if you don't already have one.

The last two touch your machine, not the repository.

> Note: `prettier-plugin-sort-json` is deliberately **not** installed, even though
> `.pre-commit-config.yaml` lists it. Nothing passes `--plugin` and the repo has no
> `.prettierrc`, so the hook never loads it either. Enabling it would sort every JSON key
> alphabetically and scramble `strings.json`, whose block order Home Assistant relies on.

## `scripts/lint`

```bash
scripts/lint [scope ...]     # default: all
```

| Scope         | Paths                                      | Checks                                                     |
| ------------- | ------------------------------------------ | ---------------------------------------------------------- |
| `integration` | `custom_components/device_link_tools/*.py` | ruff check, ruff format, pylint, pyright, docstring-linter |
| `tests`       | `tests/`                                   | same five                                                  |
| `repo`        | `**/*.{json,yaml,yml,md}`, minus `card/`   | Prettier                                                   |
| `all`         | all three                                  | everything                                                 |

The five Python checks and the two Python scopes are exactly what
`.github/workflows/lint.yml` runs, so **a green run here predicts a green CI run**. Run
it before considering work finished.

Two things to know:

- **The `repo` scope runs Prettier with `--write`**: it reformats your JSON, YAML and
  Markdown in place rather than only reporting. Everything else is read-only.
- Every check runs even after one fails, so a single invocation reports every problem at
  once. The exit code is non-zero if any of them failed.

`card/` is excluded to match the pre-commit hook: it is reserved for a vendored
third-party file meant to stay diffable against upstream (currently empty).

## `scripts/test`

Runs `pytest`, which picks up the options in `pyproject.toml`: coverage over
`custom_components/device_link_tools`, branch coverage, a missing-lines report, and
`--cov-fail-under=95`. **The suite fails if coverage drops below 95%**, so a new code
path generally needs a new test.

To run a single test while iterating, call pytest directly:

```bash
uv run --frozen pytest tests/test_services.py -q -o addopts=""   # -o addopts="" drops the coverage gate
```

## `scripts/develop`

Starts a real Home Assistant against `./config` (created on first run, and gitignored),
with `custom_components/` on `PYTHONPATH` and `--debug` on. This is how you exercise the
options flow and the repairs flow by hand — the UI paths tests cover but do not show you.

## `scripts/update_requirements`

`configuration.yaml` uses `default_config:`, which pulls in ~55 Home Assistant
integrations whose Python dependencies `pip install homeassistant` does **not** install.
This script walks the manifests reachable from `default_config` (following `dependencies`
and `after_dependencies`), collects their `requirements`, and rewrites three things from
them: the `default-config` group in `pyproject.toml`, the `ignore` list of the `uv`
ecosystem in `.github/dependabot.yml`, and `uv.lock` (by running `uv lock`). Each
generated block sits between a `BEGIN`/`END` marker pair; everything outside them,
comments included, is preserved.

Run it **whenever `homeassistant` is upgraded**, as:

```bash
uv run --frozen python scripts/update_requirements
```

It imports the _installed_ `homeassistant`, so it has to run under the venv's interpreter —
its `#!/usr/bin/env python3` shebang picks the system one, which has no Home Assistant.
Review the diff, then run `scripts/setup` to install what changed. `uv lock` failing is
the signal worth reading: it means the regenerated group contradicts something else in
the lock, which a single resolution now catches instead of a broken devcontainer later.

Home Assistant pins every one of these in its own manifests, so their versions follow the
`homeassistant` pin rather than being a free choice — a Dependabot bump would be reverted
by the next run of this script. That is why the same run regenerates the `ignore` list in
`.github/dependabot.yml`; uv's Dependabot ecosystem cannot yet filter by dependency type
([dependabot-core#13202](https://github.com/dependabot/dependabot-core/issues/13202)), so
the list has to be explicit. A few of those names (`zeroconf`, `hass-nabucasa`, `bleak`…)
are Home Assistant dependencies too, so ignoring them suppresses bumps for them
everywhere — harmless, since Home Assistant pins them exactly and the resolver would
refuse a different version anyway.
