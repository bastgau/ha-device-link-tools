# Moving the tooling to uv

Why the four `requirements*.txt` files became one `pyproject.toml` and a `uv.lock`, what
the migration buys, and what it costs. Written alongside the change, so the reasoning
survives the diff.

## What was wrong

The dev environment was installed by `pip` into whatever interpreter came first on `PATH`,
from four pinned requirement files, and every tool was then called as a bare binary
(`ruff`, `pylint`, `pyright`, `docstring-linter`, `pytest`, `hass`). `pyproject.toml` was
tool configuration only: no `[project]`, no `requires-python`. Three problems followed.

**The environment could not be rebuilt outside the devcontainer.** `homeassistant`
requires Python `>=3.14.2`. Nothing in the repository said so — the workflows asked
`actions/setup-python` for `"3.14"`, which satisfies `>=3.14.2` only by luck, and the one
real constraint (`python = ">=3.14.2,<3.15"`) sat in `pyproject.toml.poetry`, a dormant
file no tool reads. Anyone setting up on a machine whose newest Python was older had to
discover the requirement from a resolver error.

**Drift between the files was invisible.** `requirements.txt` pinned
`homeassistant==2026.9.0b3`; `pytest-homeassistant-custom-component==0.13.360` pins
_exactly the same version_ on its own. The two agreed, but nothing checked that they did —
`test.yml` never installed `requirements.txt`, so the test suite and the pin could have
drifted apart silently for a whole release cycle.

**Nothing was reproducible below the top level.** The four files pinned 7 direct
dependencies; the 149 packages actually installed were whatever the resolver picked that
day.

## What changed

| Before                                    | After                                                                |
| ----------------------------------------- | -------------------------------------------------------------------- |
| `requirements.txt`, `-lint`, `-test`      | `[project.dependencies]` + `[dependency-groups]` in `pyproject.toml` |
| no lockfile                               | `uv.lock`, committed                                                 |
| interpreter implied                       | `.python-version` (3.14.2) + `requires-python`                       |
| `pip install` into the global interpreter | `uv sync` into `./.venv`                                             |
| bare binaries on `PATH`                   | the scripts put `./.venv/bin` on `PATH` themselves                   |
| `actions/setup-python` + `cache: pip`     | `astral-sh/setup-uv` + its own cache                                 |
| `package-ecosystem: pip`                  | `package-ecosystem: uv`                                              |

The dependency groups mirror what each consumer actually needs: `lint` for the five
checks, `test` for the suite, `dev` aggregating both plus `prek`. `homeassistant` is a
project dependency rather than a group member, because three consumers need it —
`scripts/develop` runs it, and pylint and pyright resolve the integration's imports
against it — and putting it there means `--group lint` supplies it without repeating the
pin.

Two smaller consequences worth naming. `prek` moved from `requirements.txt` to the `dev`
group, so the lint workflow no longer installs a pre-commit runner it never calls. And
`docstring-linter` stays a PEP 508 direct reference to its GitHub release asset, inside
the `lint` group rather than in a `[tool.uv.sources]` table, so the line still reads the
way it did in `requirements-lint.txt`.

### The resolution did not move

Locking a set of dependencies that were previously only top-level pinned is the moment a
migration silently upgrades transitive packages. It did not happen here. Exporting the
lock and diffing it against a `pip freeze` of the pre-migration environment produced
**no version change at all** — the only extra lines are Windows- and macOS-only packages
(`colorama`, `pyobjc-*`, `winrt-*`) that a universal lock carries but Linux never
installs. `uv sync` against the new lock reported "Checked 149 packages" without
installing or removing one.

## The `default_config` packages, and why they are a group

Home Assistant's `default_config` integrations need 43 further packages (`av`, `numpy`,
`Pillow`, `SQLAlchemy`…) that only `scripts/develop` uses. They were a flat requirements
file under `.devcontainer/`, deliberately out of Dependabot's reach; they are now the
`default-config` dependency group, generated into `pyproject.toml` by
`scripts/update_requirements`.

Keeping them outside the lock had two costs. They were installed on top of the synced
venv by `uv pip install`, which knows nothing about the lock — so a pin that disagreed
with a locked version silently overrode it, and local runs could differ from CI with
nothing to notice it. And a bare `uv sync`, being exact, simply deleted them.

Inside the lock, both go away: one resolution covers everything, and a contradiction now
fails `uv lock` instead of surfacing as a broken devcontainer. The group is left out of
`default-groups`, so lint, test and CI never install 43 packages they do not import —
which is also why the scripts still sync with `--inexact`:

| Consumer                          | Command                                          | Why                                                                                 |
| --------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `scripts/setup`                   | `uv sync --group default-config`                 | the only consumer that wants the heavy group                                        |
| `scripts/lint`, `test`, `develop` | `uv sync --frozen --inexact --quiet`             | `--inexact` refuses to prune a group it does not ask for; `--frozen` locks the lock |
| `scripts/update_requirements`     | `uv run --frozen python …`                       | one call, and it needs the venv's interpreter to import `homeassistant`             |
| CI                                | `uv sync --locked --no-default-groups --group …` | `--locked` fails if the lock is stale — a freshness check for free                  |

The cost of the move is Dependabot: these pins are now in a file it scans. Home Assistant
pins them in its own manifests, so their versions follow the `homeassistant` pin — a bump
proposed here would be reverted by the next run of the generator. Since uv's ecosystem
cannot filter by dependency type ([#13202][13202]), the same generator writes the matching
`ignore` list into `.github/dependabot.yml`. Note that a few of those names (`zeroconf`,
`hass-nabucasa`, `bleak`…) are Home Assistant dependencies too, so ignoring them
suppresses bumps everywhere — harmless, since the resolver would refuse a version other
than the one Home Assistant pins.

### Why `PATH`, not `uv run`

The scripts prepend `./.venv/bin` to `PATH` instead of prefixing every call with
`uv run`. That keeps every call site unchanged — `scripts/lint` still runs bare
`ruff check …` — and the same trick maps onto CI through `$GITHUB_PATH`, which is what
keeps "a green `scripts/lint` predicts a green CI" literally true.

## What CI gains

Beyond install speed: `uv sync --locked` turns a stale lock into a failed job, so a
`pyproject.toml` edited without re-locking cannot merge. The uv cache, keyed on `uv.lock`,
covers both wheels and the resolution, where `cache: "pip"` covered only downloads and was
keyed on `requirements-lint.txt` alone — so a `homeassistant` bump never invalidated it.

The `dorny/paths-filter` lists had to move to `uv.lock` and `.python-version` in the same
commit that deleted the requirement files. Leaving them naming deleted files would make a
dependency-only pull request match nothing, report a no-op success, and turn branch
protection green on a bump that was never linted or tested.

## Dependabot: what works and what does not

Dependabot's `uv` ecosystem reads `pyproject.toml` and `uv.lock` together. The limitation
that would have made this migration a regression — updating the lock while leaving
`pyproject.toml` behind ([dependabot-core#12788][12788]) — is fixed, as is PEP 735 group
support ([#10847][10847]) and security updates falling back to pip ([#13426][13426]).

Two limitations remain, neither of which bites this repository today:

- [#13202][13202] — `dependency-type: development` / `production` does not work for uv;
  everything is treated as a production dependency. This repository's `dependabot.yml`
  uses neither `groups:` nor `dependency-type`, so nothing changes; it would only prevent
  splitting future pull requests by type.
- [#14073][14073] — with `versioning-strategy: lockfile-only`, transitive dependencies are
  not updated. That strategy is not used here.

Two things Dependabot will not do, before or after:

- **`docstring-linter` is a direct URL**, so no updater can version-track it. It was
  updated by hand before and still is.
- **`.pre-commit-config.yaml` revs are out of scope** — there is no pre-commit ecosystem.
  The `ruff` rev and the `ruff` pin are now aligned at 0.16.4 and cross-referenced by
  comment, but they will drift again. The permanent fix, not done here, is converting the
  two ruff hooks to `repo: local` entries calling `uv run --frozen ruff`, leaving the lock
  as the single source of the ruff version.

## The cost, stated plainly

The lock resolves every group together. `requirements.txt` and
`pytest-homeassistant-custom-component` pin the same Home Assistant release today; the day
a phcc release pins a newer one, `uv lock` will **fail** until `homeassistant` is bumped in
the same change. That is the drift detection working as intended, but it does mean some
Dependabot pull requests will need a second, manual commit rather than merging as they
arrive.

## Prerequisites

`uv` on `PATH`, at least 0.9 — `[tool.uv] required-version` turns an older one into a
clear error rather than mysterious behaviour, which matters because uv 0.8 silently
ignores PEP 735 groups and cannot download CPython 3.14. The interpreter itself is
downloaded by uv; an environment that sets `UV_PYTHON_DOWNLOADS=never` and has no
matching system Python will fail to sync.

[10847]: https://github.com/dependabot/dependabot-core/issues/10847
[12788]: https://github.com/dependabot/dependabot-core/issues/12788
[13202]: https://github.com/dependabot/dependabot-core/issues/13202
[13426]: https://github.com/dependabot/dependabot-core/issues/13426
[14073]: https://github.com/dependabot/dependabot-core/issues/14073
