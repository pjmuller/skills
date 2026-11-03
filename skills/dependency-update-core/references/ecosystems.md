# Ecosystem commands

Run in the branch worktree through the repo's tool manager (`mise exec -- …` when the repo uses
mise). Read-only first; the "apply" column only after selection.

**Advisories, every ecosystem at once:** `osv-scanner scan source -r .` (lockfiles: Gemfile.lock,
uv.lock, poetry/pip, pnpm/yarn/npm, go.mod, Cargo.lock, composer). `-L <lockfile>` for one file.
Container images: `osv-scanner scan image <image:tag>` after a local build. A hit is a lead: read
the advisory and check we use the affected code path.

**GitHub Dependabot alerts** (already computed when enabled):
`gh api 'repos/<owner>/<repo>/dependabot/alerts?state=open&per_page=100' --paginate --jq '.[] | [.security_advisory.severity, .dependency.manifest_path, .dependency.package.name] | @tsv'`.
Group by `manifest_path`: only the wrapper's in-scope manifests count. Docs sites, prototypes or
copied skill cores (`.agents/skills/*-core/…`) are someone else's: name them in the report, fix a
core in its source repo, not the copy.

| Ecosystem | Outdated / inventory | Apply exactly the selection | Notes |
| --- | --- | --- | --- |
| Ruby (bundler) | `bundle outdated --only-explicit`; `bundle-audit check --update` | `bundle update --conservative <gems…>` | `--conservative` keeps shared deps still; paid gem sources need their env token |
| Python (uv) | `uv tree --outdated --depth 1`; `uv pip list --outdated` | `uv lock --upgrade-package <pkg>` (repeat), then `uv sync` | git-pinned deps: bump the rev deliberately, never via `--upgrade` |
| Node (pnpm) | `pnpm outdated`; `pnpm audit` | `pnpm update <pkg>` (in range) / `pnpm add <pkg>@<ver>` | yarn/npm repos: their `outdated`/`upgrade`, don't switch managers here |
| Go | `go list -m -u all`; `govulncheck ./...` | `go get <mod>@<ver> && go mod tidy` | `go` directive / toolchain line = runtime pin |
| Runtimes | version files (`mise.toml`, `.ruby-version`, `.python-version`, `.nvmrc`, `go.mod`), CI setup steps, Dockerfile `FROM` | bump all pins of one runtime together | patch releases within the line are Should; a new minor/major line is a migration |
| Container base images | every `FROM`, compose `image:`, CI `services:` | same tag in every place, or deliberate digest pin | `:latest` / floating tags: pin with reason (reproducible builds) |
| Databases / caches | dev compose, CI services, production engine version (read-only cloud CLI) | dev/CI to match production; production engine upgrades are a separate ops change, ticket only | major engine upgrades never ride along |
| Deploy tooling | Kamal / buildpacks / PaaS stack / IaC versions in config and CI | bump config + CI pin together | deploy behaviour changes are tested only by a human deploy: say so in the ticket |

Primary sources to cite: the project's GitHub releases or CHANGELOG, its security page or GHSA,
the runtime vendor's maintenance page (ruby-lang.org, python.org devguide, nodejs.org releases,
go.dev/doc/devel/release), the database vendor's versioning policy, cloud provider deprecation
calendars.
