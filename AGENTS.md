# AGENTS

## Document Routing (Mandatory)

- `AGENTS.md` only keeps central-repo execution guards, release discipline, and the managed contract entrypoint.
- `docs/USAGE.md` is the maintainer runbook for day-to-day operations, release publishing, downstream apply, and downstream onboarding.
- `README.md` stays as the short repository entrypoint.
- `./.workflow-kit/WORKFLOW_CONTRACT.md` is the single detailed source for managed workflow rules.
- If workflow behavior changes, update `AGENTS.md` and `docs/USAGE.md` in the same change set.

## Central Release Discipline (Mandatory)

This repository is the central source of truth for downstream managed workflow files:

- Primary repository root: `/Users/pi/PyCharmProject/AgentWorkflowKit`
- Normal code edits belong in managed worktrees attached to this repo; the primary checkout is reserved for orchestration, publishing, downstream apply, and merge/release handling.
- Git workflow runtime sources live in `.workflow-kit/` and `.githooks/`.
- Templates under `templates/full_codex_flow/files/.workflow-kit/` and `templates/full_codex_flow/files/.githooks/` are generated artifacts, not the primary editing target.
- Downstream `PublicWorkRegisterService` runtime files are also managed here via the profile template at `templates/full_codex_flow/files/src/main/python/public_work_register_service.py.tmpl`.
- If you change `.workflow-kit/`, `.githooks/`, `profiles/`, `repos/`, or release tooling in `scripts/`, publish a new release before expecting downstream auto-apply to succeed.
- 下游仓库中的受管 `.workflow-kit/` / `.githooks/` 默认应保持纳入版本控制，中央 apply 不再把它们写入 `.git/info/exclude`。
- 下游仓库的项目级 `.venv` 仍应保持本地运行时，不纳入版本控制；受管脚本负责在 worktree 中自动补共享 `.venv` 软链接，并同步维护 worktree 级 `.git/info/exclude`，避免新 worktree 在自动 sync 前被误判为 dirty。
- 默认分支探测以仓库 manifest 中声明的 `default_branch` 为准；只要该分支已存在，本地脚本不应因为陈旧的 `origin/HEAD` 继续回退到旧默认分支。

Required sequence for workflow changes:

```bash
python3 scripts/export_templates.py --repo-id AgentWorkflowKit
python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>
```

- `PublicWorkRegister` directory selection must stay bound to the canonical project directory, not a worktree-specific folder name.
- `scripts/apply_downstreams.py` refuses to run when current release artifacts are stale relative to the source repo.
- `scripts/apply_downstreams.py` now creates downstream local commits in child-repo worktrees; it does not push or auto-release those downstream commits.
- 中央仓库的 downstream apply 顺序固定为：`测试 -> 审查 -> commit -> push/auto-release -> apply_downstreams.py`。
- `scripts/apply_downstreams.py` 现在支持 `--repo-id <RepoId>` 与 `--resume-existing-worktree`，用于单仓恢复失败的 fan-out worktree。
- `session_push_autorelease.sh` 会在 `<default-branch>` push 成功后再执行 `python3 scripts/apply_downstreams.py`，避免在 auto-release 前提早 fan-out。
- 为兼容旧版下游 runtime，中央 downstream apply 在调用子仓 `new_worktree.sh` 时会临时设置 `SKIP_SHARED_VENV_LINK=1`；待当前 release 应用完成后，再由新 runtime 补做共享 `.venv` 修复。
- 下游 `AGENTS.md` 中散落的通用 workflow 章节会在 apply 时刷洗并收束到固定 managed block；块外应只保留仓库特有规则。
- Therefore, “changed workflow source but did not publish release yet” is an invalid handoff state for downstream sync.
- Use `docs/USAGE.md` for the full release/apply/onboarding runbook.

## Operator Policy (Mandatory)

- Once user intent is explicit, execute by default and do not ask repeated confirmation unless the action is destructive, requirements remain ambiguous, or an environment prerequisite is missing.
- Full managed workflow behavior, commit gates, and troubleshooting rules live in `./.workflow-kit/WORKFLOW_CONTRACT.md`.

<!-- workflow-kit:agents:start -->
## Managed Workflow Contract

- Run `./.workflow-kit/assert_workspace.sh` before substantive work.
- Code edits belong on `codex/*` managed worktrees rather than the primary/default-branch checkout.
- For code changes, follow `test -> review -> ./.workflow-kit/prepare_commit.sh -> git commit`.
- Full workflow rules: `./.workflow-kit/WORKFLOW_CONTRACT.md`.
<!-- workflow-kit:agents:end -->
