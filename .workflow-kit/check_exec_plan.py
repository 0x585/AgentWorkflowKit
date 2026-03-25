#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.30
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/check_exec_plan.py
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLAN_SECTION_TITLE = "开工计划"
PLAN_FIELD_ORDER = (
    "工作类型",
    "目标",
    "改动范围",
    "实施步骤",
    "预期验证",
    "已知风险/阻塞",
)
ACTIVE_EXEC_PATTERN = re.compile(r"^docs/exec_records/([0-9]{4,})(?:_commit\.txt|\.md)$")
CONTINUE_WORK_TYPE_PATTERN = re.compile(r"^续作\((?P<branch>codex/[A-Za-z0-9._/-]+)/(?P<exec_id>[0-9]{4,})\)$")

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )


class ExecPlanService:
    def discover_active_exec_ids(self, repo_root: Path) -> list[int]:
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
        active_exec_ids: list[int] = []
        seen: set[int] = set()
        for raw_line in status.stdout.splitlines():
            line = raw_line.rstrip("\n")
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            match = ACTIVE_EXEC_PATTERN.fullmatch(path.strip())
            if match is None:
                continue
            exec_id = int(match.group(1))
            if exec_id in seen:
                continue
            seen.add(exec_id)
            active_exec_ids.append(exec_id)
        return active_exec_ids

    def validate(self, repo_root: Path, exec_id: int | None = None) -> dict[str, object]:
        active_exec_ids = self.discover_active_exec_ids(repo_root)
        issues: list[str] = []

        resolved_exec_id = exec_id
        if resolved_exec_id is None:
            if not active_exec_ids:
                issues.append("当前 worktree 没有活动 exec；先运行 ./.workflow-kit/start_exec.sh。")
            elif len(active_exec_ids) > 1:
                issues.append(
                    "当前 worktree 存在多个活动 exec："
                    + ", ".join(str(value) for value in active_exec_ids)
                    + "；请先整理到单一活动 exec。"
                )
            else:
                resolved_exec_id = active_exec_ids[0]

        record_path = repo_root / "docs" / "exec_records" / f"{resolved_exec_id}.md" if resolved_exec_id is not None else None
        if resolved_exec_id is None or record_path is None:
            return {
                "valid": False,
                "exec_id": resolved_exec_id,
                "record_path": None if record_path is None else str(record_path),
                "active_exec_ids": active_exec_ids,
                "issues": issues,
            }

        if not record_path.is_file():
            issues.append(f"执行记录不存在：{record_path}")
            return {
                "valid": False,
                "exec_id": resolved_exec_id,
                "record_path": str(record_path),
                "active_exec_ids": active_exec_ids,
                "issues": issues,
            }

        text = record_path.read_text(encoding="utf-8")
        fields = self._extract_plan_fields(text)
        if fields is None:
            issues.append(f"章节未完成：## {PLAN_SECTION_TITLE}")
        else:
            for field_name in PLAN_FIELD_ORDER:
                if field_name not in fields:
                    issues.append(f"章节缺少字段：## {PLAN_SECTION_TITLE} / {field_name}")
                    continue
                value = fields[field_name].strip()
                if not value or "TODO" in value:
                    issues.append(f"章节字段未完成：## {PLAN_SECTION_TITLE} / {field_name}")

            work_type = fields.get("工作类型", "").strip()
            if work_type and work_type != "新需求":
                if CONTINUE_WORK_TYPE_PATTERN.fullmatch(work_type) is None:
                    issues.append(
                        "章节字段格式非法：## 开工计划 / 工作类型 "
                        "必须为“新需求”或“续作(codex/<branch>/<exec_id>)”。"
                    )

        return {
            "valid": not issues,
            "exec_id": resolved_exec_id,
            "record_path": str(record_path),
            "active_exec_ids": active_exec_ids,
            "issues": issues,
        }

    def _extract_plan_fields(self, text: str) -> dict[str, str] | None:
        section_pattern = re.compile(
            rf"^## {re.escape(PLAN_SECTION_TITLE)}\n(?P<body>.*?)(?=^## |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = section_pattern.search(text)
        if match is None:
            return None

        field_names = "|".join(re.escape(name) for name in PLAN_FIELD_ORDER)
        fields: dict[str, str] = {}
        for field_match in re.finditer(
            rf"(?ms)^- (?P<field>{field_names})：(?P<value>.*?)(?=^- (?:{field_names})：|\Z)",
            match.group("body"),
        ):
            fields[field_match.group("field").strip()] = field_match.group("value").strip()
        return fields


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the required exec start-plan block.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--exec-id", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = ExecPlanService().validate(args.repo_root, args.exec_id)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["valid"]:
        return 0

    record_path = result.get("record_path") or "<unknown>"
    print(f"[exec-plan] 开工计划未完成：{record_path}", file=sys.stderr)
    print("[exec-plan] 先补齐 `## 开工计划`，再继续正式编码或提交。", file=sys.stderr)
    for issue in result["issues"]:
        print(f"[exec-plan] {issue}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
