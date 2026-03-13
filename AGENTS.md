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
./.workflow-kit/assert_workspace.sh
```

If it fails, stop immediately and fix the workspace first.

## Session Start Default (Mandatory)

When switching into a `codex/*` branch, hook `.githooks/post-checkout` automatically tries to sync the branch to latest `origin/<default-branch>`:

- It runs `./.workflow-kit/session_sync.sh <default-branch>`.
- If workspace is dirty or sync fails, it only warns and does not block checkout.
- You can check current sync relationship via `./.workflow-kit/session_sync_status.sh`.
- `./.workflow-kit/new_exec.sh` still runs sync by default before allocating execution ID (use `--no-sync` only for internal/special flows).

## Git Hooks Enable (Mandatory)

- Hooks must be enabled in this repository: `git config core.hooksPath .githooks`.
- Prefer one-shot setup: `./.workflow-kit/setup_githooks.sh`.
- In `ASSERT_PURPOSE=code` mode, hooks misconfiguration is a hard failure in `.workflow-kit/assert_workspace.sh`.
- In default mode, hooks misconfiguration only warns to avoid blocking read-only operations.

## Central Release Discipline (Mandatory)

This repository is the central source of truth for downstream managed workflow files:

- Git workflow runtime sources live in `.workflow-kit/` and `.githooks/`.
- Templates under `templates/full_codex_flow/files/.workflow-kit/` and `templates/full_codex_flow/files/.githooks/` are generated artifacts, not the primary editing target.
- Downstream `PublicWorkRegisterService` runtime files are also managed here via the profile template at `templates/full_codex_flow/files/src/main/python/public_work_register_service.py.tmpl`.
- If you change `.workflow-kit/`, `.githooks/`, `profiles/`, `repos/`, or release tooling in `scripts/`, publish a new release before expecting downstream auto-apply to succeed.
- Downstream apply removes legacy managed `.git_scripts/*` and managed workflow `scripts/*` wrappers; project-owned callers must target `.workflow-kit/*`.
- 下游仓库中的受管 `.workflow-kit/` / `.githooks/` 默认应保持纳入版本控制，中央 apply 不再把它们写入 `.git/info/exclude`。
- 下游仓库的项目级 `.venv` 仍应保持本地运行时，不纳入版本控制；受管脚本负责在 worktree 中自动补共享 `.venv` 软链接，并同步维护 worktree 级 `.git/info/exclude`，避免新 worktree 在自动 sync 前被误判为 dirty。
- 默认分支探测以仓库 manifest 中声明的 `default_branch` 为准；只要该分支已存在，本地脚本不应因为陈旧的 `origin/HEAD` 继续回退到旧默认分支。

Required sequence for workflow changes:

```bash
python3 scripts/export_templates.py --repo-id AgentWorkflowKit
python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>
```

- `PublicWorkRegister` directory selection must stay bound to the canonical project directory, not a worktree-specific folder name.

- `.githooks/post-commit` runs `python3 scripts/apply_downstreams.py`.
- `scripts/apply_downstreams.py` refuses to run when current release artifacts are stale relative to the source repo.
- `scripts/apply_downstreams.py` now creates downstream local commits in child-repo worktrees; it does not push or auto-release those downstream commits.
- 为兼容旧版下游 runtime，中央 downstream apply 在调用子仓 `new_worktree.sh` 时会临时设置 `SKIP_SHARED_VENV_LINK=1`；待当前 release 应用完成后，再由新 runtime 补做共享 `.venv` 修复。
- 下游 `AGENTS.md` 中散落的通用 workflow 章节会在 apply 时刷洗并收束到固定 managed block；块外应只保留仓库特有规则。
- Therefore, “changed workflow source but did not publish release yet” is an invalid handoff state for downstream sync.
- Use `docs/USAGE.md` for the full release/apply/onboarding procedure.

## Session End Default (Mandatory)

After finishing code changes on `codex/*`, run:

```bash
git commit -m "[<exec_id>] <type>(<scope>): <summary>"
```

- `.githooks/post-commit` first attempts downstream apply via `python3 scripts/apply_downstreams.py`.
- `.githooks/post-commit` then auto-runs `git push` for `codex/*` branches by default.
- Downstream apply creates local child-repo commits only; any resulting downstream worktree still requires later push/release handling in that child repo.
- `.githooks/pre-push` auto-triggers `./.workflow-kit/session_push_autorelease.sh` for `codex/*` pushes.
- Flow: push `codex/*` -> merge into `<default-branch>` -> push `<default-branch>` -> delete remote/local source branch -> remove source worktree.
- If auto-release reports `behind/diverged`, run `./.workflow-kit/session_sync.sh <default-branch>` first, then retry push/release.
- If you need to commit without downstream auto-apply (special cases only), use `SKIP_APPLY_DOWNSTREAMS_AFTER_COMMIT=1 git commit ...`.
- If you need to commit without auto push (special cases only), use `SKIP_AUTO_PUSH_AFTER_COMMIT=1 git commit ...`.
- No second confirmation is required.
- If merge conflicts occur, conflict context is kept and resumed via `./.workflow-kit/session_release_resume.sh`.
- Auto-release success means this task worktree is removed; for next task create/switch to a new `codex/*` worktree first.

## Code Edit Guard (Mandatory)

For manual guard checks before code/file edits, run:

```bash
ASSERT_PURPOSE=code ./.workflow-kit/assert_workspace.sh
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
- Any worktree marked abnormal by `.workflow-kit/assert_workspace.sh` until it is resolved/cleaned.
- Any workflow-source change that is handed to downstream apply without publishing a matching release first.

<!-- workflow-kit:agents:start -->
## Managed Workflow Contract

- Profile: `full_codex_flow`
- Workflow version: `1.0.15`
- Workflow source metadata: `.workflow-kit/source.json`
- Canonical managed runtime entrypoints live under `.workflow-kit/`.
- Before substantive work, run the repository workflow guard entrypoint: `./.workflow-kit/assert_workspace.sh`.
- Managed git hooks live under `.githooks/`; keep `core.hooksPath=.githooks`.
- Legacy managed `.git_scripts/*` and workflow `scripts/*` wrappers are removed during release apply; project-owned callers should invoke `.workflow-kit/*` directly.
- Code edits belong on `codex/*` managed worktrees rather than the default-branch primary checkout.
- Commit messages use `[<exec_id>] <type>(<scope>): <summary>`; if this repository enables auto-push/auto-release hooks, `git commit` may trigger them.
- Do not manually edit managed workflow files in this repository.
- Repo-specific differences must be implemented through the central manifest, not by local customization.
- Managed entrypoints run locally first; only after a failure do they check the published central release, auto-apply if outdated, and retry once.
<!-- workflow-kit:agents:end -->
