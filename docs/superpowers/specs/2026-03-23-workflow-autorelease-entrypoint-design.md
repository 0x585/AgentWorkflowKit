# Workflow Autorelease Entrypoint Design

**Goal:** 把 `codex/*` 分支提交后的自动发布入口统一收口到 `session_push_autorelease.sh`，修复首次无 upstream 时的自动发布失败，并补强 merge conflict 恢复诊断与维护者文档。

## 背景

当前 `post-commit` 只会直接执行 `git push`。这条路径依赖分支已经具备 upstream tracking，且把真正的自动发布逻辑分散到 `pre-push` 与 `session_push_autorelease.sh`。当新建的 `codex/*` 分支第一次提交、尚未建立 upstream 时，`post-commit` 会直接失败，导致后续 auto-release 没有机会执行。

同时，冲突恢复虽然已经有 `session_release_resume.sh`，但状态提示偏弱，维护者需要自己判断当前卡在“冲突未解”“主仓上下文不匹配”还是“已经 merge 完成但尚未清理”等阶段。

## 设计决策

### 1. 统一入口

`post-commit` 不再自行执行裸 `git push`，而是在满足 `codex/*`、工作树干净等前置条件后，直接调用 `./.workflow-kit/session_push_autorelease.sh`。

这样：

- 首次 push 会稳定走 `git push -u origin <branch>`
- merge / push 默认分支 / downstream apply 由同一入口统一编排
- 维护者不再需要理解 “post-commit -> pre-push -> session_push_autorelease” 这条分叉链路

`pre-push` 仍保留兼容触发逻辑，供手动执行 `git push` 的场景使用，但不再是 post-commit 自动化的主入口。

### 2. 冲突恢复补强

`session_push_autorelease.sh` 与 `session_release_resume.sh` 将补充更明确的阶段提示：

- 当前是否处于 conflict state
- 当前需要在哪个仓、哪个分支恢复
- 主仓 dirty / branch mismatch / merge context mismatch 时的建议动作
- merge 已完成但 state file 仍残留时的可理解反馈

目标是让维护者只看脚本输出，就能知道下一步该执行什么。

### 3. 文档与发布纪律

因为这是中央 workflow 行为变更，必须同步更新：

- `AGENTS.md`
- `docs/USAGE.md`

并在代码通过验证后发布一个新的 `full_codex_flow` release，再应用到下游仓。

## 影响范围

- `.githooks/post-commit`
- `.workflow-kit/session_push_autorelease.sh`
- `.workflow-kit/session_release_resume.sh`
- `docs/USAGE.md`
- `AGENTS.md`
- `tests/test_workflow_release.py`
- 由 release 发布生成的 `profiles/full_codex_flow/*` 与模板工件

## 验证策略

- 单测覆盖 `post-commit` 改为直接触发 autorelease 入口
- 单测覆盖无 upstream 场景下仍可完成 release
- 单测覆盖 conflict resume 诊断文案
- 发布新 release 后再执行中央仓的 release 校验与下游 apply
