# Managed Workflow Contract

- Profile: `full_codex_flow`
- Workflow version: `1.0.22`
- Workflow source metadata: `.workflow-kit/source.json`

## Overview

- Managed workflow entrypoints live under `.workflow-kit/`; managed hooks live under `.githooks/`.
- Run `./.workflow-kit/assert_workspace.sh` before substantive work.
- Code edits belong on `codex/*` managed worktrees rather than the primary/default-branch checkout.
- Keep generic workflow guidance in this contract; keep only repository-specific rules outside the managed blocks in `README.md` and `AGENTS.md`.

## Required Flow

1. Start from a workspace that passes the managed guard.
2. For code changes, begin with `./.workflow-kit/start_exec.sh "<summary>"`, complete `## 开工计划`, then follow `test -> review -> ./.workflow-kit/prepare_task_commit.sh -> git commit`.
3. Keep `docs/exec_records/<exec_id>.md` updated before committing.
4. If the repository enables auto-push or auto-release, let the managed hooks finish the remaining push, release, and apply steps.

## Code-Task Guardrails

- `ASSERT_PURPOSE=code ./.workflow-kit/assert_workspace.sh` is the manual pre-edit guard.
- In code mode, the guard requires a valid `codex/*` worktree and rejects detached `HEAD`, abnormal worktrees, or default-branch worktrees.
- Use `./.workflow-kit/session_sync.sh <default-branch>` when auto-release reports `behind` or `diverged`.
- If merge or release conflicts pause automation, resume with `./.workflow-kit/session_release_resume.sh`.

## Commit Gate Rules

- Commit messages use `[<exec_id>] <type>(<scope>): <summary>`.
- `./.workflow-kit/start_exec.sh` is the supported code-task start entrypoint; `new_exec.sh` is a lower-level allocator for managed automation and special flows.
- Before `git commit`, run `./.workflow-kit/prepare_task_commit.sh`; `./.workflow-kit/prepare_commit.sh` remains the lower-level readiness helper, and `--stage` should be used only when the commit should intentionally include every current change.
- Unless the user explicitly asks to pause first, once validation/review has passed and no remaining commit gate blocks progress, Codex should finish `./.workflow-kit/prepare_task_commit.sh -> git commit` in the current turn rather than handing off a modified-but-uncommitted workspace.
- Every exec record that enters the managed commit flow must complete `## 开工计划`; `工作类型` must be either `新需求` or explicit `续作(codex/<branch>/<exec_id>)`.
- Code-task exec records must complete `验证结果` and `审查结果` before `commit-msg` can pass.
- `验证结果` must record `命令`、`范围`、`结果`、`未覆盖项`、`提交快照`.
- `审查结果` must record `审查方式`、`结论`、`残余风险`、`提交快照`.
- Keep each required field header on its own `- 字段：...` line, but the field body may continue on following lines when one line is not enough.
- After the final staging pass, refresh both `提交快照` fields so they match the current staged snapshot.
- Managed `pre-commit` blocks commits when unstaged tracked changes or untracked files remain; `SKIP_PREPARE_COMMIT_GUARD=1` bypasses only that readiness check.

## Managed Runtime Notes

- Managed entrypoints run locally first; only after a failure do they check the published central release, auto-apply if outdated, and retry once.
- Managed git hooks expect `core.hooksPath=.githooks`.
- `new_worktree.sh` creates the managed worktree only; create or resume the exec explicitly with `start_exec.sh`.
- Legacy managed workflow entrypoints and managed `scripts/*` wrappers are removed during release apply; project-owned callers should invoke `.workflow-kit/*` directly.
- Downstream managed `.workflow-kit/` and `.githooks/` stay under version control; project-level `.venv` stays local, and managed scripts repair shared worktree `.venv` links plus worktree-level `.git/info/exclude`.
- Repositories should not locally customize managed workflow files; workflow-wide changes belong in the central manifest and release flow.

## Troubleshooting Pointers

- Start gate check: `./.workflow-kit/check_exec_plan.py`.
- Manual close-up status: `./.workflow-kit/prepare_task_commit.sh --json`.
- Lower-level readiness helper: `./.workflow-kit/prepare_commit.sh --json`.
- Snapshot refresh helper: `python3 ./.workflow-kit/exec_record_hygiene.py --sync-staged-snapshot --exec-id <exec_id>`.
- Use documented `SKIP_*` environment variables only for exceptional flows that intentionally bypass automation steps.
- For a manual upgrade or re-apply, rerun the workflow source repository recorded in `.workflow-kit/source.json` against the target repository.
