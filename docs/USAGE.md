# AgentWorkflowKit 使用说明

本文面向维护 `AgentWorkflowKit` 的开发者，说明这个项目的职责、日常使用方式，以及如何新增一个子应用（下游仓库）。

## 0. 文档分工

为了避免规则分散，当前分工如下：

- `README.md`
  仓库入口、项目定位、常用命令入口
- `AGENTS.md`
  执行时必须遵守的守卫、提交规则、release 纪律
- `docs/USAGE.md`
  维护者操作手册，包括发布、下发、校验、接入新子应用

如果 workflow 行为发生变化，通常至少要一起更新：

- `AGENTS.md`
- `docs/USAGE.md`

## 1. 项目定位

`AgentWorkflowKit` 是 Git 工作流资产的中央仓库，统一维护：

- `full_codex_flow` profile 的 release 版本
- 受管 git hooks
- 受管 git 工作流脚本
- 下游 `PublicWorkRegisterService` 运行时实现
- 下游仓库配置
- 发布、应用、校验工具

## 2. Source Of Truth

当前约定如下：

- 中央仓库里的 git 工作流源码在 `.workflow-kit/` 和 `.githooks/`
- 模板产物在 `templates/full_codex_flow/files/.workflow-kit/` 和 `templates/full_codex_flow/files/.githooks/`
- 下游 `PublicWorkRegisterService` 模板在 `templates/full_codex_flow/files/src/main/python/public_work_register_service.py.tmpl`
- 完整受管 workflow 规则统一收敛在 `./.workflow-kit/WORKFLOW_CONTRACT.md`
- 发布 release 时，`scripts/publish_release.py` 会先把源码导出回模板，再生成新的 release 工件

说明：

- 下游仓库中的 `.workflow-kit/` 和 `.githooks/` 由本项目自动生成
- 下游仓库中的 `.workflow-kit/` 和 `.githooks/` 由下游仓库正常纳入版本控制，便于审查和回滚
- 下游仓库中的项目级 `.venv` 不纳入版本控制；新 worktree 通过受管脚本自动补指向主仓共享环境的软链接，并在对应 worktree 的 `.git/info/exclude` 中登记这些链接，避免被 `session_sync` 误判为脏工作区
- 下游仓库原本用于应用自身逻辑的 `scripts/` 会继续保留，但它们不再承载受管 workflow wrapper
- git 工作流相关的受管入口统一固定在 `.workflow-kit/`
- 中央仓库自身的 `PublicWorkRegister` 脚本依赖 `src/main/python/agent_workflow_kit/tooling/service/public_work_register_service.py`
- 下游仓库中的 `src/main/python/<python_package_name>/tooling/service/public_work_register_service.py` 也由中央仓库统一下发，不应在子项目里各自分叉维护
- 下游 `public_work_register_sync.py` / `public_work_register_claim.py` 中涉及 Python 包路径的位置，也必须跟随 repo manifest 的 `python_package_name` 展开，不能回退到中央仓自身包名

## 3. 目录说明

- `profiles/full_codex_flow/profile.json`
  说明 profile 管理哪些文件
- `repos/*.json`
  说明每个下游仓库的路径和 repo-specific 参数
- `.workflow-kit/`
  中央仓库中的 git 工作流源码
- `.githooks/`
  中央仓库中的 hooks 源码
- `templates/full_codex_flow/files/`
  发布用模板产物
- `scripts/publish_release.py`
  发布新版本 release
- `scripts/apply_release.py`
  应用当前 release 到单个仓库
- `scripts/apply_downstreams.py`
  为所有需要更新的下游仓库创建本地 worktree 提交
- `scripts/check_release.py`
  校验某个仓库是否和当前 release 一致

## 4. 日常维护流程

### 4.1 修改 git 工作流源码

如果你要修改受管的 hooks 或 git 工作流脚本，请直接改：

- `.workflow-kit/`
- `.githooks/`

不要直接改：

- `templates/full_codex_flow/files/.workflow-kit/`
- `templates/full_codex_flow/files/.githooks/`

因为模板会在发布时自动从源码重新导出。

### 4.1.1 执行入口

中央仓和下游仓统一遵循 `./.workflow-kit/WORKFLOW_CONTRACT.md` 中的完整执行规则。这里仅保留维护中央仓时最常用的两个收口入口：

- `./.workflow-kit/prepare_commit.sh`
- `python3 ./.workflow-kit/exec_record_hygiene.py --sync-staged-snapshot --exec-id <exec_id>`

对代码任务，只要 `验证结果`、`审查结果` 都已完成，且没有剩余 commit gate 阻塞，Codex 默认应在当前回合继续执行 `./.workflow-kit/prepare_commit.sh` 与 `git commit`，不要停在“已修改但未 commit”的状态；只有用户明确要求暂停，或 gate 尚未通过时，才保留未提交现场。

执行记录里的结构化字段仍然必须保留固定表头，例如 `- 命令：...`、`- 范围：...`、`- 结果：...`、`- 未覆盖项：...`，但字段正文不再要求必须单行；如果一行放不下，可以直接在后续行继续补充说明。

如果需要查看完整的代码任务顺序、workspace 守卫、commit gate 或异常恢复语义，直接查阅 contract，不再在本手册里重复维护第二份完整合同。

### 4.2 导出模板

如果你只是想先本地查看模板导出结果，可以执行：

```bash
python3 scripts/export_templates.py --repo-id AgentWorkflowKit
```

### 4.3 发布新 release

当源码修改稳定后，发布新的 workflow 版本：

```bash
python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>
```

这一步会做三件事：

1. 把 `.workflow-kit/` 和 `.githooks/` 导出回模板
2. 更新 `profiles/full_codex_flow/release.json`
3. 更新 `profiles/full_codex_flow/managed-files.lock.json` 以及对应历史版本目录

### 4.4 应用到单个仓库

```bash
python3 scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/AgentTask --repo-id AgentTask
```

应用后会自动：

- 生成下游仓库的 `.workflow-kit/`
- 生成下游仓库的 `.githooks/`
- 让 `new_worktree` / `post-checkout` / `new_exec` 自动修复 worktree 的共享 `.venv` 软链接
- 同步维护 worktree 级 `.git/info/exclude`，让共享 `.venv` 软链接不会出现在 `git status` 中
- 生成下游仓库的 `src/main/python/<python_package_name>/tooling/service/public_work_register_service.py`
- 删除旧版受管 workflow 入口文件
- 删除旧版受管 `scripts/*` workflow wrapper；项目脚本若仍需调用 workflow，必须直接调用 `./.workflow-kit/*`
- 刷洗 `AGENTS.md` / `README.md` 中散落的通用 workflow 文案，把中央受管 workflow 说明收束到固定 managed block
- 清理旧的 workflow-kit managed `.git/info/exclude` block（如果存在）
- 设置 `core.hooksPath=.githooks`

### 4.5 应用到所有下游仓库

```bash
python3 scripts/apply_downstreams.py
```

注意：

- 这条命令只会在当前 release 工件和源码状态一致时执行
- 如果当前 release 已经过期，会提示你先重新发布
- 对于 `current` 状态的子仓库，会直接跳过，不会创建空提交
- 对于 `outdated` / `drift` 状态的子仓库，会在子仓库主目录旁创建 `*-wt-*` worktree，应用当前 release，完成自动审查，并在没有阻断问题时直接提交后 auto-release 合并到下游默认分支
- 如果子仓库缺失 `.workflow-kit/new_worktree.sh`，该子仓会直接失败并返回错误
- 为兼容仍在旧 runtime 上的子仓库，中央 fan-out 创建 worktree 时会先临时跳过共享 `.venv` 链接，待新 release 应用完成后再补做修复
- 自动审查当前会执行 `git diff --check` 与 `scripts/check_release.py --json`，确认受管文件已经与当前 release 对齐；这一步不自动运行子仓项目测试
- 如果 auto-release 成功，命令输出会返回下游 source commit、最终 merge 到默认分支后的 main sha，并自动清理下游 `workflow-release-*` 分支与 worktree
- 如果 auto-release 被环境条件阻塞，例如下游主仓不干净、同步落后或出现 merge 冲突，会保留本地 worktree 与分支供恢复，并把该子仓记为失败
- 如果只想重跑某个失败子仓库，可以用 `python3 scripts/apply_downstreams.py --repo-id <RepoId>`
- 如果该子仓库已经存在未完成的 `workflow-release-*` worktree，可再加 `--resume-existing-worktree` 继续使用原 worktree 恢复 fan-out
- 如果某个子仓库失败，其他子仓库仍会继续处理，但最终命令会返回非零退出码

### 4.6 校验仓库状态

```bash
python3 scripts/check_release.py --repo-root /Users/pi/PyCharmProject/AgentTask --repo-id AgentTask --json
```

常见状态：

- `current`：与当前 release 一致
- `outdated`：已安装版本落后于当前 release
- `drift`：本地受管文件被改动，和已安装 release 不一致
- `invalid`：元数据或路径异常

下游仓库的受管入口现在默认优先直接执行本地脚本，不会在每次调用前都回中央仓库做版本核对。只有入口执行失败时，`workflow_guard` 才会补做版本检查；workspace 限制、自动 apply 边界和失败重试语义统一见 `./.workflow-kit/WORKFLOW_CONTRACT.md`。

## 5. 中央仓库提交后的自动行为

中央仓库代码任务的默认自动顺序现在是：

```bash
git commit
git push
./.workflow-kit/session_push_autorelease.sh
python3 scripts/apply_downstreams.py
```

这表示：

- `.githooks/post-commit` 在 `codex/*` 分支上只负责自动执行 `git push`
- `.githooks/pre-push` 会接管这个 push，调用 `./.workflow-kit/session_push_autorelease.sh`
- `session_push_autorelease.sh` 会先完成 merge / push 默认分支，再调用 `python3 scripts/apply_downstreams.py`
- 只要当前 release 工件是最新的，中央仓库 auto-release 成功后会自动为需要更新的下游仓库创建 fan-out worktree，完成自动审查，并在无阻塞问题时直接把下游变更 merge 到各自默认分支
- 如果你只是修改了源码但还没有发布新的 release，这个自动动作会拒绝执行，并提示先发布
- 如果某个下游仓库的 auto-release 被阻塞，对应 `workflow-release-*` worktree 会被保留，后续可在该子仓中继续恢复或手动处理

如果你临时不想触发自动应用，可以在当前命令前加：

```bash
SKIP_APPLY_DOWNSTREAMS_AFTER_COMMIT=1 git commit ...
```

如果你需要跳过当前仓库的全部 `post-commit` 自动化，可以使用：

```bash
SKIP_POST_COMMIT_AUTOMATION=1 git commit ...
```

## 6. 如何新增一个子应用

这里的“子应用”指新增一个受本项目管理的下游仓库。

### 6.1 准备下游仓库

先确认下游仓库已经存在，并且有自己的 `.git/`：

- 仓库路径已经确定
- 默认分支已经确定，例如 `main` 或 `master`
- 应用自己的源码目录已经确定

### 6.2 新增 repo 配置

在 `repos/` 下新增一个 JSON 文件，文件名通常和 `repo_id` 一致。

示例：

```json
{
  "repo_id": "MyNewApp",
  "profile": "full_codex_flow",
  "expected_workspace_root": "/Users/pi/PyCharmProject/MyNewApp",
  "default_branch": "main",
  "python_package_name": "my_new_app",
  "compile_main_path": "src/main/python/my_new_app",
  "compile_test_path": "src/test/python/my_new_app",
  "public_work_register_dir": "/Users/pi/PyCharmProject/PublicWorkRegister/MyNewApp"
}
```

字段说明：

- `repo_id`
  下游仓库唯一标识
- `profile`
  当前一般使用 `full_codex_flow`
- `expected_workspace_root`
  下游仓库本地绝对路径
- `default_branch`
  下游默认分支
  受管脚本会优先采用这里声明的默认分支；只要对应分支已经存在，即使仓库本地 `origin/HEAD` 还没刷新，也不会回退到旧默认分支
- `python_package_name`
  Python 包名，用于受管 Python 脚本中的导入
- `compile_main_path`
  pre-push 时的主代码编译检查目录
- `compile_test_path`
  pre-push 时的测试代码编译检查目录
- `public_work_register_dir`
  对应公共工作登记目录
  必须填写项目级固定目录，例如 `/Users/pi/PyCharmProject/PublicWorkRegister/MyNewApp`
  不能填写 `MyNewApp-wt-*` 这类 worktree 专属目录；运行时会按 git common dir 归一回主项目目录

### 6.3 发布新版本

新增 `repos/<RepoId>.json` 后，发布一个新的 workflow 版本：

```bash
python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>
```

这样新的子应用就会被纳入 release 清单。

### 6.4 应用到新子应用

```bash
python3 scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/MyNewApp --repo-id MyNewApp
```

如果你希望一起刷新所有下游，也可以执行：

```bash
python3 scripts/apply_downstreams.py
```

### 6.5 校验是否接入成功

```bash
python3 scripts/check_release.py --repo-root /Users/pi/PyCharmProject/MyNewApp --repo-id MyNewApp --json
```

预期结果应为：

```json
{
  "status": "current"
}
```

### 6.6 下游仓库接入后的表现

接入成功后，下游仓库会新增：

- `.workflow-kit/`
- `.workflow-kit/`
- `.githooks/`

同时：

- `core.hooksPath` 会自动指向 `.githooks`
- 应用自身原有的 `scripts/` 目录不会被整体删除
- 只有旧版受管 git 工作流脚本会从 `scripts/` 中移除

## 7. 推荐操作顺序

如果你修改了中央仓库并希望稳定下发，推荐顺序如下：

1. 修改 `.workflow-kit/` 或 `.githooks/`
2. 运行 `python3 scripts/export_templates.py --repo-id AgentWorkflowKit`
3. 运行必要测试
4. 发布新版本 `python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>`
5. 应用到下游 `python3 scripts/apply_downstreams.py`
6. 用 `scripts/check_release.py` 验证结果

## 8. 常见问题

### 8.1 为什么下游的 `.workflow-kit/` 和 `.githooks/` 现在要进版本控制？

因为它们虽然由中央仓库生成，但仍然是下游仓库的实际运行入口。纳入版本控制后，评审、回滚、bisect 和工作区复制都会更直接，也能避免 worktree 因本地 exclude 而缺失运行文件。

### 8.2 为什么项目 `.venv` 不建议纳入版本控制？

因为 `.venv` 是本地运行时产物，强依赖机器环境、Python 小版本和二进制依赖。把它放进 Git 会显著放大仓库体积和提交噪音。当前 workflow 改为在新 worktree 创建、`codex/*` checkout 和 `new_exec` 时自动修复指向主仓共享环境的 `.venv` 软链接，用共享环境解决 worktree 缺少解释器的问题。

### 8.3 为什么保留了下游的 `scripts/`？

下游应用自身可能还有非 git 工作流用途的脚本。为了不影响现有应用逻辑，只迁移受管 git 工作流相关脚本。

### 8.4 修改了中央仓库源码，为什么自动下游应用没有执行？

通常是因为你还没有发布新 release。`scripts/apply_downstreams.py` 只接受“当前 release 工件与源码一致”的状态。
