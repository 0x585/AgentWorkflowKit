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
- 下游仓库配置
- 发布、应用、校验工具

## 2. Source Of Truth

当前约定如下：

- 中央仓库里的 git 工作流源码在 `.git_scripts/` 和 `.githooks/`
- 模板产物在 `templates/full_codex_flow/files/.git_scripts/` 和 `templates/full_codex_flow/files/.githooks/`
- 发布 release 时，`scripts/publish_release.py` 会先把源码导出回模板，再生成新的 release 工件

说明：

- 下游仓库中的 `.git_scripts/` 和 `.githooks/` 由本项目自动生成
- 下游仓库中的 `.git_scripts/` 和 `.githooks/` 会写入 `.git/info/exclude`，不参与版本控制
- 下游仓库原本用于应用自身逻辑的 `scripts/` 会继续保留
- 只有 git 工作流相关的受管脚本会迁移到 `.git_scripts/`
- 中央仓库自身的 `PublicWorkRegister` 脚本依赖 `src/main/python/agent_workflow_kit/tooling/service/public_work_register_service.py`

## 3. 目录说明

- `profiles/full_codex_flow/profile.json`
  说明 profile 管理哪些文件
- `repos/*.json`
  说明每个下游仓库的路径和 repo-specific 参数
- `.git_scripts/`
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
  应用当前 release 到所有下游仓库
- `scripts/check_release.py`
  校验某个仓库是否和当前 release 一致

## 4. 日常维护流程

### 4.1 修改 git 工作流源码

如果你要修改受管的 hooks 或 git 工作流脚本，请直接改：

- `.git_scripts/`
- `.githooks/`

不要直接改：

- `templates/full_codex_flow/files/.git_scripts/`
- `templates/full_codex_flow/files/.githooks/`

因为模板会在发布时自动从源码重新导出。

### 4.2 导出模板

如果你只是想先本地查看模板导出结果，可以执行：

```bash
python3 scripts/export_templates.py --repo-id AgentWorkflowKit
```

### 4.3 发布新 release

当源码修改稳定后，发布新的 workflow 版本：

```bash
python3 scripts/publish_release.py --profile full_codex_flow --version 1.0.3
```

这一步会做三件事：

1. 把 `.git_scripts/` 和 `.githooks/` 导出回模板
2. 更新 `profiles/full_codex_flow/release.json`
3. 更新 `profiles/full_codex_flow/managed-files.lock.json` 以及对应历史版本目录

### 4.4 应用到单个仓库

```bash
python3 scripts/apply_release.py --repo-root /Users/pi/PyCharmProject/AgentTask --repo-id AgentTask
```

应用后会自动：

- 生成下游仓库的 `.git_scripts/`
- 生成下游仓库的 `.githooks/`
- 清理旧版受管 `scripts/*` git 工作流脚本
- 写入 `.git/info/exclude`
- 设置 `core.hooksPath=.githooks`

### 4.5 应用到所有下游仓库

```bash
python3 scripts/apply_downstreams.py
```

注意：

- 这条命令只会在当前 release 工件和源码状态一致时执行
- 如果当前 release 已经过期，会提示你先重新发布

### 4.6 校验仓库状态

```bash
python3 scripts/check_release.py --repo-root /Users/pi/PyCharmProject/AgentTask --repo-id AgentTask --json
```

常见状态：

- `current`：与当前 release 一致
- `outdated`：已安装版本落后于当前 release
- `drift`：本地受管文件被改动，和已安装 release 不一致
- `invalid`：元数据或路径异常

下游仓库的受管入口现在默认优先直接执行本地脚本，不会在每次调用前都回中央仓库做版本核对。只有入口执行失败时，`workflow_guard` 才会补做版本检查；如果发现只是版本落后，会自动应用最新已发布 release 并重试一次。

## 5. 中央仓库提交后的自动行为

中央仓库自己的 `.githooks/post-commit` 会在提交后尝试执行：

```bash
python3 scripts/apply_downstreams.py
```

这表示：

- 只要当前 release 工件是最新的，中央仓库提交后会自动把当前 release 应用到下游仓库
- 如果你只是修改了源码但还没有发布新的 release，这个自动动作会拒绝执行，并提示先发布

如果你临时不想触发自动应用，可以在当前命令前加：

```bash
SKIP_APPLY_DOWNSTREAMS_AFTER_COMMIT=1 git commit ...
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
python3 scripts/publish_release.py --profile full_codex_flow --version 1.0.3
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
- `.git_scripts/`
- `.githooks/`

同时：

- `.git/info/exclude` 会自动忽略 `.git_scripts/` 和 `.githooks/`
- `core.hooksPath` 会自动指向 `.githooks`
- 应用自身原有的 `scripts/` 目录不会被整体删除
- 只有旧版受管 git 工作流脚本会从 `scripts/` 中移除

## 7. 推荐操作顺序

如果你修改了中央仓库并希望稳定下发，推荐顺序如下：

1. 修改 `.git_scripts/` 或 `.githooks/`
2. 运行 `python3 scripts/export_templates.py --repo-id AgentWorkflowKit`
3. 运行必要测试
4. 发布新版本 `python3 scripts/publish_release.py --profile full_codex_flow --version <new-version>`
5. 应用到下游 `python3 scripts/apply_downstreams.py`
6. 用 `scripts/check_release.py` 验证结果

## 8. 常见问题

### 8.1 为什么下游的 `.git_scripts/` 和 `.githooks/` 不进版本控制？

因为它们是中央仓库生成的受管产物，不是下游仓库手工维护的源码。

### 8.2 为什么保留了下游的 `scripts/`？

下游应用自身可能还有非 git 工作流用途的脚本。为了不影响现有应用逻辑，只迁移受管 git 工作流相关脚本。

### 8.3 修改了中央仓库源码，为什么自动下游应用没有执行？

通常是因为你还没有发布新 release。`scripts/apply_downstreams.py` 只接受“当前 release 工件与源码一致”的状态。
