# Workflow Autorelease Entrypoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 `codex/*` 提交后的自动发布入口到 `session_push_autorelease.sh`，并补强冲突恢复诊断、文档和发布工件。

**Architecture:** `post-commit` 只负责把受管条件下的提交交给 `session_push_autorelease.sh`；真正的 push / merge / downstream apply 继续由 autorelease 脚本集中编排。冲突恢复逻辑仍由 `session_release_resume.sh` 承接，但会补足上下文提示，降低人工恢复成本。

**Tech Stack:** Bash, Python unittest, managed workflow release tooling

---

### Task 1: 收口 post-commit 自动入口

**Files:**
- Modify: `.githooks/post-commit`
- Modify: `tests/test_workflow_release.py`

- [ ] **Step 1: 写失败测试，约束 post-commit 直接调用 autorelease**

在 `tests/test_workflow_release.py` 增加一个用例，mock/替换 worktree 里的 `session_push_autorelease.sh`，执行 `.githooks/post-commit` 后断言：

- 不再依赖 `git push`
- 会直接调用 `session_push_autorelease.sh`
- 传递成功输出给调用方

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest tests.test_workflow_release.WorkflowReleaseTest.test_post_commit_runs_session_push_autorelease_directly`
Expected: FAIL，说明当前 hook 仍在走旧入口

- [ ] **Step 3: 最小改动实现新入口**

更新 `.githooks/post-commit`：

- 保留 `codex/*`、dirty tree、skip env 等前置守卫
- 将主动作改为执行 `"$ROOT/.workflow-kit/session_push_autorelease.sh" --source-branch "$CURRENT_BRANCH" --target "$DEFAULT_BRANCH"`
- 失败时仍返回可操作提示

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python3 -m unittest tests.test_workflow_release.WorkflowReleaseTest.test_post_commit_runs_session_push_autorelease_directly`
Expected: PASS

### Task 2: 补强 autorelease 与 resume 诊断

**Files:**
- Modify: `.workflow-kit/session_push_autorelease.sh`
- Modify: `.workflow-kit/session_release_resume.sh`
- Modify: `tests/test_workflow_release.py`

- [ ] **Step 1: 写失败测试，覆盖恢复文案与边界**

增加用例覆盖：

- conflict state 存在时的阻断提示
- `session_release_resume.sh` 在 state file 缺失/分支不对/冲突未解时的输出
- `session_release_resume.sh` 在完成 merge 后的清理输出

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest tests.test_workflow_release.WorkflowReleaseTest.test_session_release_resume_reports_missing_state_with_guidance`
Expected: FAIL

- [ ] **Step 3: 实现诊断与恢复提示优化**

更新两个脚本的输出：

- 明确 source branch / target branch / primary root / source worktree
- 在 block 场景中追加建议命令
- 保持现有状态文件协议兼容

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python3 -m unittest tests.test_workflow_release.WorkflowReleaseTest.test_session_release_resume_reports_missing_state_with_guidance`
Expected: PASS

### Task 3: 更新维护文档

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/USAGE.md`

- [ ] **Step 1: 更新中央仓纪律说明**

把中央仓的自动行为说明改成：

- `post-commit` 直接触发 `session_push_autorelease.sh`
- `pre-push` 保留为手动 push 的兼容入口
- 冲突恢复的推荐命令与时机

- [ ] **Step 2: 复查文档语义与代码一致**

Run: `rg -n "post-commit|pre-push|session_push_autorelease|session_release_resume" AGENTS.md docs/USAGE.md`
Expected: 文档表述和新链路一致

### Task 4: 发布新 release 并应用到下游

**Files:**
- Modify: `profiles/full_codex_flow/release.json`
- Modify: `profiles/full_codex_flow/managed-files.lock.json`
- Create/Modify: `profiles/full_codex_flow/releases/<version>/...`

- [ ] **Step 1: 运行中央仓测试**

Run: `python3 -m unittest tests.test_workflow_release`
Expected: PASS

- [ ] **Step 2: 导出模板并发布 release**

Run: `python3 scripts/export_templates.py --repo-id AgentWorkflowKit`
Run: `python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>`
Expected: release 工件更新完成

- [ ] **Step 3: 校验 release 工件**

Run: `python3 scripts/check_release.py --repo-root /Users/pi/PyCharmProject/AgentWorkflowKit --repo-id AgentWorkflowKit --json`
Expected: `status=current`

- [ ] **Step 4: 提交中央仓变更**

Run: `./.workflow-kit/prepare_commit.sh --json`
Run: `git commit`
Expected: 中央仓变更提交成功

- [ ] **Step 5: auto-release 并应用到目标下游**

Run: 由 `post-commit` / `session_push_autorelease.sh` 自动完成；必要时补执行 `python3 scripts/apply_downstreams.py --repo-id AgentTransitStation`
Expected: `AgentTransitStation` 收到新 release
