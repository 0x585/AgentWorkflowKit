# AgentWorkflowKit

Central source of truth for managed git workflow assets.

## What It Owns

- Release versioning for the `full_codex_flow` profile
- Managed hooks and git workflow scripts
- Repo-specific manifests for downstream repositories
- Apply/check/publish tooling

## Source Of Truth

- The runnable git workflow sources live in `.git_scripts/` and `.githooks/`
- `templates/full_codex_flow/files/.git_scripts/` and `templates/full_codex_flow/files/.githooks/` are exported from those runtime files
- `python3 scripts/publish_release.py ...` automatically refreshes the templates before building a release

## Usage

Quick links:

- [docs/USAGE.md](docs/USAGE.md)
- [AGENTS.md](AGENTS.md)

Publish the current profile:

```bash
python3 scripts/publish_release.py --profile full_codex_flow --version <version>
```

Apply the latest release to a downstream repository:

```bash
python3 scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/AgentTask
python3 scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/AgentTransitStation
```

Check whether a downstream repository matches the published release:

```bash
python3 scripts/check_release.py --repo-root /Users/pi/PyCharmProject/AgentTask --json
```

<!-- workflow-kit:readme:start -->
## Managed Git Workflow

- Managed by `AgentWorkflowKit`
- Profile: `full_codex_flow`
- Workflow version: `1.0.2`
- Central repo: `/Users/pi/PyCharmProject/AgentWorkflowKit`
- This repository must not locally customize managed git workflow files.
- If the installed version does not match the published central version, managed entrypoints auto-upgrade before continuing.
- Manual resync:

```bash
python3 /Users/pi/PyCharmProject/AgentWorkflowKit/scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/AgentWorkflowKit
```
<!-- workflow-kit:readme:end -->
