# AgentWorkflowKit

Central source of truth for managed git workflow assets.

## What It Owns

- Release versioning for the `full_codex_flow` profile
- Managed hooks and git workflow scripts
- Repo-specific manifests for downstream repositories
- Apply/check/publish tooling
- Central repo runtime helpers used by managed scripts, including the shared `PublicWorkRegisterService` source for this repository and downstream apps

## Source Of Truth

- The runnable git workflow sources live in `.workflow-kit/` and `.githooks/`
- `templates/full_codex_flow/files/.workflow-kit/` and `templates/full_codex_flow/files/.githooks/` are exported from those runtime files
- `python3 scripts/publish_release.py ...` automatically refreshes the templates before building a release
- Detailed managed workflow rules live in `./.workflow-kit/WORKFLOW_CONTRACT.md`

## Usage

Quick links:

- [docs/USAGE.md](docs/USAGE.md)
- [AGENTS.md](AGENTS.md)
- [./.workflow-kit/WORKFLOW_CONTRACT.md](./.workflow-kit/WORKFLOW_CONTRACT.md)

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

The central repository itself uses `/Users/pi/PyCharmProject/PublicWorkRegister/AgentWorkflowKit` as the canonical shared register root, and `AgentWorkflowKit-wt-*` worktrees resolve back to that same directory.

<!-- workflow-kit:readme:start -->
## Managed Git Workflow

- This repository is managed by `full_codex_flow`.
- Full workflow rules: `./.workflow-kit/WORKFLOW_CONTRACT.md`.
- Workflow version: `1.0.22`; source metadata: `.workflow-kit/source.json`.
<!-- workflow-kit:readme:end -->
