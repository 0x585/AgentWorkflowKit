# AGENTS

## Document Routing (Mandatory)

- `AGENTS.md` only defines execution-time guards, mandatory workflow constraints, and submission rules.
- `docs/USAGE.md` is the maintainer runbook for day-to-day operations, release publishing, downstream apply, and downstream onboarding.
- `README.md` stays as the short repository entrypoint.
- If workflow behavior changes, update `AGENTS.md` and `docs/USAGE.md` in the same change set.

## Workspace Guard (Mandatory)

Primary repository root:

- `/Users/pi/PyCharmProject/AgentWorkflowKit`

Before any substantive work, run:

```bash
./.git_scripts/assert_workspace.sh
```

If it fails, stop immediately and fix the workspace first.

## Session Start Default (Mandatory)

When switching into a `codex/*` branch, hook `.githooks/post-checkout` automatically tries to sync the branch to latest `origin/<default-branch>`:

- It runs `./.git_scripts/session_sync.sh <default-branch>`.
- If workspace is dirty or sync fails, it only warns and does not block checkout.
- You can check current sync relationship via `./.git_scripts/session_sync_status.sh`.
- `./.git_scripts/new_exec.sh` still runs sync by default before allocating execution ID (use `--no-sync` only for internal/special flows).

## Git Hooks Enable (Mandatory)

- Hooks must be enabled in this repository: `git config core.hooksPath .githooks`.
- Prefer one-shot setup: `./.git_scripts/setup_githooks.sh`.
- In `ASSERT_PURPOSE=code` mode, hooks misconfiguration is a hard failure in `.git_scripts/assert_workspace.sh`.
- In default mode, hooks misconfiguration only warns to avoid blocking read-only operations.

## Central Release Discipline (Mandatory)

This repository is the central source of truth for downstream managed workflow files:

- Git workflow runtime sources live in `.git_scripts/` and `.githooks/`.
- Templates under `templates/full_codex_flow/files/.git_scripts/` and `templates/full_codex_flow/files/.githooks/` are generated artifacts, not the primary editing target.
- Downstream `PublicWorkRegisterService` runtime files are also managed here via the profile template at `templates/full_codex_flow/files/src/main/python/public_work_register_service.py.tmpl`.
- If you change `.git_scripts/`, `.githooks/`, `profiles/`, `repos/`, or release tooling in `scripts/`, publish a new release before expecting downstream auto-apply to succeed.

Required sequence for workflow changes:

```bash
python3 scripts/export_templates.py --repo-id AgentWorkflowKit
python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>
```

- `PublicWorkRegister` directory selection must stay bound to the canonical project directory, not a worktree-specific folder name.

- `.githooks/post-commit` runs `python3 scripts/apply_downstreams.py`.
- `scripts/apply_downstreams.py` refuses to run when current release artifacts are stale relative to the source repo.
- Therefore, “changed workflow source but did not publish release yet” is an invalid handoff state for downstream sync.
- Use `docs/USAGE.md` for the full release/apply/onboarding procedure.

## Session End Default (Mandatory)

After finishing code changes on `codex/*`, run:

```bash
git commit -m "[<exec_id>] <type>(<scope>): <summary>"
```

- `.githooks/post-commit` first attempts downstream apply via `python3 scripts/apply_downstreams.py`.
- `.githooks/post-commit` then auto-runs `git push` for `codex/*` branches by default.
- `.githooks/pre-push` auto-triggers `./.git_scripts/session_push_autorelease.sh` for `codex/*` pushes.
- Flow: push `codex/*` -> merge into `<default-branch>` -> push `<default-branch>` -> delete remote/local source branch -> remove source worktree.
- If auto-release reports `behind/diverged`, run `./.git_scripts/session_sync.sh <default-branch>` first, then retry push/release.
- If you need to commit without downstream auto-apply (special cases only), use `SKIP_APPLY_DOWNSTREAMS_AFTER_COMMIT=1 git commit ...`.
- If you need to commit without auto push (special cases only), use `SKIP_AUTO_PUSH_AFTER_COMMIT=1 git commit ...`.
- No second confirmation is required.
- If merge conflicts occur, conflict context is kept and resumed via `./.git_scripts/session_release_resume.sh`.
- Auto-release success means this task worktree is removed; for next task create/switch to a new `codex/*` worktree first.

## Code Edit Guard (Mandatory)

For manual guard checks before code/file edits, run:

```bash
ASSERT_PURPOSE=code ./.git_scripts/assert_workspace.sh
```

Code/file edits are allowed in attached worktrees:

- `AgentWorkflowKit-wt-*`
- `/Users/pi/.codex/worktrees/*/AgentWorkflowKit`

Additional rules (enforced by the guard script):

- Branch must use `codex/*` in `ASSERT_PURPOSE=code` mode.
- Default branch is reserved for primary repository only; worktrees must not checkout default branch.
- The primary repository is for orchestration, publishing, applying downstream releases, and merge/release handling; do not perform normal code edits there.
- Default flow cleans up the source worktree after commit auto-release; reuse only applies when auto-release is explicitly bypassed.

## Execution Confirmation Policy (Mandatory)

- Once user intent is explicit (e.g. "按标准处理", "继续", "直接处理"), execute by default and do not ask repeated confirmation.
- Asking for confirmation is only allowed in three cases:
  - destructive action with irreversible impact
  - unresolved requirement ambiguity that blocks implementation
  - missing permission/environment prerequisite
- `git commit` on `codex/*` is expected to trigger downstream apply, auto-push, then auto-release; original push may be intentionally canceled by hook after release succeeds.

## Disallowed States

- Detached `HEAD` in `ASSERT_PURPOSE=code` mode.
- Any worktree not attached to `/Users/pi/PyCharmProject/AgentWorkflowKit`.
- Any worktree marked abnormal by `.git_scripts/assert_workspace.sh` until it is resolved/cleaned.
- Any workflow-source change that is handed to downstream apply without publishing a matching release first.

<!-- workflow-kit:agents:start -->
## Central Workflow Release (Managed)

- Managed by `AgentWorkflowKit`
- Profile: `full_codex_flow`
- Workflow version: `1.0.4`
- Central repo: `/Users/pi/PyCharmProject/AgentWorkflowKit`
- Do not manually edit managed workflow files in this repository.
- Repo-specific differences must be implemented through the central manifest, not by local customization.
- Managed entrypoints run locally first; only after a failure do they check the published central release, auto-apply if outdated, and retry once.
<!-- workflow-kit:agents:end -->
