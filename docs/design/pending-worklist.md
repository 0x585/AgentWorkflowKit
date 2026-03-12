# 待处理清单

这份清单用于维护当前 `AgentWorkflowKit` 还未收口的工作项。

维护方式：

- `Decision` 表示后续处理策略
- `Status` 表示当前进度
- 新增项时保持 `ID` 唯一，便于后续引用和讨论
- Codex 推进待办前，必须同步共享登记：
  - 共享登记基目录固定为 `/Users/pi/PyCharmProject/PublicWorkRegister`
  - 当前项目登记目录固定为 `/Users/pi/PyCharmProject/PublicWorkRegister/AgentWorkflowKit`
  - 项目目录名按同一 git common dir 归一，`AgentWorkflowKit-wt-*` 等附属 worktree 必须共用 `AgentWorkflowKit`

字段约定：

- `Priority`: `P0` / `P1` / `P2` / `P3`
- `Decision`: `EXECUTE` / `DEFER` / `DROP`
- `Status`: `PENDING` / `IN_PROGRESS` / `BLOCKED`
## 当前清单

| ID | Priority | Decision | Status | 工作项 | 说明 |
|---|---|---|---|---|---|
| W001 | P1 | DEFER | PENDING | 梳理中央仓库自身 PublicWorkRegister 的长期使用方式 | 当前已补 service 与项目级共享目录归一，后续再决定是否把更多 workflow 维护待办纳入共享登记 |

## 使用建议

- 如果某项要立即推进，把 `Decision` 保持为 `EXECUTE`
- 如果某项本阶段先不做，把 `Decision` 改成 `DEFER`
- 如果确认不再需要，把 `Decision` 改成 `DROP`
