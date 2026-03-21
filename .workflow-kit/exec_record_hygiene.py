#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.22
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/exec_record_hygiene.py
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SECTION_FIELD_ORDER = {
    "验证结果": ("命令", "范围", "结果", "未覆盖项", "提交快照"),
    "审查结果": ("审查方式", "结论", "残余风险", "提交快照"),
}

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )


class ExecRecordHygieneService:
    def audit_placeholders(self, repo_root: Path, target_branch: str) -> dict[str, object]:
        records_dir = repo_root / "docs" / "exec_records"
        index_path = records_dir / "INDEX.md"
        placeholder_ids: list[int] = []
        for record_path in sorted(records_dir.glob("[0-9][0-9][0-9][0-9]*.md")):
            match = re.fullmatch(r"([0-9]{4,})\.md", record_path.name)
            if match is None:
                continue
            exec_id = int(match.group(1))
            if self._is_placeholder_exec(repo_root=repo_root, target_branch=target_branch, exec_id=exec_id):
                placeholder_ids.append(exec_id)
        reusable_exec_id = max(placeholder_ids) if placeholder_ids else None
        cleanup_exec_ids = [exec_id for exec_id in placeholder_ids if exec_id != reusable_exec_id]
        return {
            "records_dir": str(records_dir),
            "index_path": str(index_path),
            "placeholder_exec_ids": placeholder_ids,
            "reusable_exec_id": reusable_exec_id,
            "cleanup_exec_ids": cleanup_exec_ids,
        }

    def cleanup_placeholders(self, repo_root: Path, target_branch: str, keep_exec_id: int | None = None) -> dict[str, object]:
        audit = self.audit_placeholders(repo_root, target_branch)
        placeholder_ids = [int(exec_id) for exec_id in audit.get("placeholder_exec_ids", [])]
        cleanup_ids = placeholder_ids if keep_exec_id is None else [exec_id for exec_id in placeholder_ids if exec_id != int(keep_exec_id)]
        removed_paths: list[str] = []
        records_dir = repo_root / "docs" / "exec_records"
        for exec_id in cleanup_ids:
            for path in (records_dir / f"{exec_id}.md", records_dir / f"{exec_id}_commit.txt"):
                if path.exists():
                    path.unlink()
                    removed_paths.append(str(path))
        self._remove_index_rows(repo_root=repo_root, exec_ids=cleanup_ids)
        return {
            "cleanup_exec_ids": cleanup_ids,
            "removed_paths": removed_paths,
            "kept_exec_id": keep_exec_id,
        }

    def _is_placeholder_exec(self, repo_root: Path, target_branch: str, exec_id: int) -> bool:
        if exec_id in self._committed_exec_ids(repo_root):
            return False
        records_dir = repo_root / "docs" / "exec_records"
        record_path = records_dir / f"{exec_id}.md"
        commit_template_path = records_dir / f"{exec_id}_commit.txt"
        if not record_path.is_file() or not commit_template_path.is_file():
            return False
        if record_path.read_text(encoding="utf-8") != self._record_template(exec_id, target_branch):
            return False
        if commit_template_path.read_text(encoding="utf-8") != self._commit_template(exec_id):
            return False
        return self._index_has_todo_row(repo_root=repo_root, exec_id=exec_id)

    def _committed_exec_ids(self, repo_root: Path) -> set[int]:
        try:
            output = subprocess.check_output(
                ["git", "-C", str(repo_root), "log", "--all", "--format=%s"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return set()
        committed: set[int] = set()
        for line in output.splitlines():
            match = re.match(r"^\[([0-9]{4,})\]\s", line.strip())
            if match is not None:
                committed.add(int(match.group(1)))
        return committed

    def _index_has_todo_row(self, repo_root: Path, exec_id: int) -> bool:
        index_path = repo_root / "docs" / "exec_records" / "INDEX.md"
        if not index_path.is_file():
            return False
        pattern = re.compile(rf"^\|\s*{exec_id}\s*\|\s*[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\s*\|\s*TODO\s*\|")
        return any(pattern.fullmatch(line.strip()) for line in index_path.read_text(encoding="utf-8").splitlines())

    def _remove_index_rows(self, repo_root: Path, exec_ids: list[int]) -> None:
        if not exec_ids:
            return
        index_path = repo_root / "docs" / "exec_records" / "INDEX.md"
        if not index_path.is_file():
            return
        ids = {int(exec_id) for exec_id in exec_ids}
        kept_lines: list[str] = []
        pattern = re.compile(r"^\|\s*([0-9]{4,})\s*\|")
        for line in index_path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match is not None and int(match.group(1)) in ids:
                continue
            kept_lines.append(line)
        index_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")

    def _record_template(self, exec_id: int, target_branch: str) -> str:
        return (
            f"# {exec_id}\n\n"
            "## 完成定义（DoD）\n\n"
            f"- [ ] 需求目标已明确（含“是否必须 merge 到 {target_branch} 并删除分支”）\n"
            "- [ ] 若有代码修改：已执行测试并记录结果\n"
            "- [ ] 若有代码修改：已完成变更审查并记录结论\n"
            "- [ ] 若为代码任务：已 push / auto-release，并完成下游应用\n\n"
            "## 需求摘要\n\n"
            "TODO\n\n"
            "## 变更文件\n\n"
            "- TODO\n\n"
            "## 变更说明\n\n"
            "- TODO\n\n"
            "## 验证结果\n\n"
            "- 命令：TODO\n"
            "- 范围：TODO\n"
            "- 结果：TODO\n"
            "- 未覆盖项：TODO\n"
            "- 提交快照：TODO\n\n"
            "## 审查结果\n\n"
            "- 审查方式：TODO\n"
            "- 结论：TODO\n"
            "- 残余风险：TODO\n"
            "- 提交快照：TODO\n\n"
            "## 完成待办项\n\n"
            "- 无\n\n"
            "## 当前占用待办项\n\n"
            "- 无\n\n"
            "## 风险与回滚\n\n"
            "- TODO\n"
        )

    def _commit_template(self, exec_id: int) -> str:
        return (
            f"[{exec_id}] type(scope): summary\n\n"
            "# Changes\n# - TODO\n\n"
            "# Tests\n"
            "# - 命令：TODO\n"
            "# - 范围：TODO\n"
            "# - 结果：TODO\n"
            "# - 未覆盖项：TODO\n"
            "# - 提交快照：TODO\n\n"
            "# Review\n"
            "# - 审查方式：TODO\n"
            "# - 结论：TODO\n"
            "# - 残余风险：TODO\n"
            "# - 提交快照：TODO\n\n"
            "# Risks\n# - TODO\n"
        )

    def validate_commit_flow(self, repo_root: Path, exec_id: int, staged_paths: list[str]) -> dict[str, object]:
        record_path = repo_root / "docs" / "exec_records" / f"{exec_id}.md"
        requires_test_review = any(not self._is_doc_only_path(path) for path in staged_paths)
        current_staged_snapshot = self.current_staged_snapshot(repo_root)
        result: dict[str, object] = {
            "exec_id": exec_id,
            "record_path": str(record_path),
            "staged_paths": staged_paths,
            "requires_test_review": requires_test_review,
            "current_staged_snapshot": current_staged_snapshot,
            "missing_items": [],
        }
        if not requires_test_review:
            return result

        if not record_path.is_file():
            result["missing_items"] = [f"Execution record missing: {record_path}"]
            return result

        text = record_path.read_text(encoding="utf-8")
        missing_items: list[str] = []
        required_checkboxes = (
            "若有代码修改：已执行测试并记录结果",
            "若有代码修改：已完成变更审查并记录结论",
        )
        for item in required_checkboxes:
            pattern = re.compile(rf"^- \[x\] {re.escape(item)}\s*$", re.MULTILINE)
            if pattern.search(text) is None:
                missing_items.append(f"完成定义缺少勾选：{item}")

        missing_items.extend(self._validate_structured_section(text, "验证结果", current_staged_snapshot))
        missing_items.extend(self._validate_structured_section(text, "审查结果", current_staged_snapshot))

        result["missing_items"] = missing_items
        return result

    def current_staged_snapshot(self, repo_root: Path) -> str:
        process = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--cached",
                "--binary",
                "--no-ext-diff",
                "--",
                ".",
                ":(exclude)docs/exec_records/**",
            ],
            check=True,
            capture_output=True,
        )
        return hashlib.sha256(process.stdout).hexdigest()

    def sync_staged_snapshot(self, repo_root: Path, exec_id: int) -> dict[str, object]:
        record_path = repo_root / "docs" / "exec_records" / f"{exec_id}.md"
        if not record_path.is_file():
            raise FileNotFoundError(f"Execution record missing: {record_path}")
        current_staged_snapshot = self.current_staged_snapshot(repo_root)
        text = record_path.read_text(encoding="utf-8")
        for section_title in SECTION_FIELD_ORDER:
            text = self._upsert_section_field(text, section_title, "提交快照", current_staged_snapshot)
        record_path.write_text(text, encoding="utf-8")
        return {
            "exec_id": exec_id,
            "record_path": str(record_path),
            "current_staged_snapshot": current_staged_snapshot,
        }

    def _is_doc_only_path(self, path: str) -> bool:
        normalized = PurePosixPath(path).as_posix()
        if not normalized:
            return True
        if normalized.startswith("docs/exec_records/"):
            return True
        if normalized in {"README.md", "AGENTS.md"}:
            return True
        if normalized.startswith("docs/") and PurePosixPath(normalized).suffix.lower() in {".md", ".mdx", ".rst", ".txt"}:
            return True
        if normalized.startswith("templates/") and "/blocks/" in normalized and normalized.endswith(".md.tmpl"):
            return True
        return False

    def _extract_section_body(self, text: str, section_title: str) -> str | None:
        section_pattern = re.compile(
            rf"^## {re.escape(section_title)}\n(?P<body>.*?)(?=^## |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = section_pattern.search(text)
        if match is None:
            return None
        return match.group("body")

    def _structured_field_pattern(self, section_title: str, field_name: str | None = None) -> re.Pattern[str]:
        all_field_names = "|".join(re.escape(name) for name in SECTION_FIELD_ORDER[section_title])
        selected_field_names = all_field_names if field_name is None else re.escape(field_name)
        return re.compile(
            rf"(?ms)^- (?P<field>{selected_field_names})：(?P<value>.*?)(?=^- (?:{all_field_names})：|\Z)"
        )

    def _extract_structured_section_fields(self, text: str, section_title: str) -> dict[str, str] | None:
        body = self._extract_section_body(text, section_title)
        if body is None:
            return None
        fields: dict[str, str] = {}
        for match in self._structured_field_pattern(section_title).finditer(body):
            fields[match.group("field").strip()] = match.group("value").strip()
        return fields

    def _validate_structured_section(self, text: str, section_title: str, current_staged_snapshot: str) -> list[str]:
        fields = self._extract_structured_section_fields(text, section_title)
        if fields is None:
            return [f"章节未完成：## {section_title}"]
        missing_items: list[str] = []
        for field_name in SECTION_FIELD_ORDER[section_title]:
            if field_name not in fields:
                missing_items.append(f"章节缺少字段：## {section_title} / {field_name}")
                continue
            value = fields[field_name]
            if not value or "TODO" in value:
                missing_items.append(f"章节字段未完成：## {section_title} / {field_name}")
                continue
            if field_name == "提交快照" and value != current_staged_snapshot:
                missing_items.append(f"提交快照不匹配：## {section_title}")
        return missing_items

    def _upsert_section_field(self, text: str, section_title: str, field_name: str, value: str) -> str:
        section_pattern = re.compile(
            rf"(^## {re.escape(section_title)}\n)(?P<body>.*?)(?=^## |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = section_pattern.search(text)
        if match is None:
            raise RuntimeError(f"Section not found: {section_title}")
        body = match.group("body")
        field_pattern = self._structured_field_pattern(section_title, field_name)
        replacement = f"- {field_name}：{value}\n"
        field_match = field_pattern.search(body)
        if field_match is not None:
            updated_body = body[: field_match.start()] + replacement + body[field_match.end() :]
        else:
            suffix = "" if body.endswith("\n") or not body else "\n"
            updated_body = f"{body}{suffix}{replacement}"
        return text[: match.start("body")] + updated_body + text[match.end("body") :]

    def _git_output(self, repo_root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit and cleanup placeholder exec record residue.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--target-branch")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reuse-latest", action="store_true")
    parser.add_argument("--check-commit-flow", action="store_true")
    parser.add_argument("--sync-staged-snapshot", action="store_true")
    parser.add_argument("--exec-id", type=int)
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = ExecRecordHygieneService()
    if args.check_commit_flow:
        if args.exec_id is None:
            raise SystemExit("--exec-id is required with --check-commit-flow")
        result = service.validate_commit_flow(args.repo_root, args.exec_id, list(args.paths))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        missing_items = list(result.get("missing_items", []))
        if missing_items:
            print("[commit-msg] Code changes require test -> review -> commit.", file=sys.stderr)
            print(f"[commit-msg] Update {result['record_path']} before retrying.", file=sys.stderr)
            print(f"[commit-msg] Current staged snapshot: {result['current_staged_snapshot']}", file=sys.stderr)
            print("[commit-msg] Refresh both '提交快照' fields after final staging.", file=sys.stderr)
            for item in missing_items:
                print(f"[commit-msg] {item}", file=sys.stderr)
            return 1
        return 0

    if args.sync_staged_snapshot:
        if args.exec_id is None:
            raise SystemExit("--exec-id is required with --sync-staged-snapshot")
        result = service.sync_staged_snapshot(args.repo_root, args.exec_id)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["current_staged_snapshot"])
        return 0

    if not args.target_branch:
        raise SystemExit("--target-branch is required unless using --check-commit-flow or --sync-staged-snapshot")

    audit = service.audit_placeholders(args.repo_root, args.target_branch)
    reusable_exec_id = audit.get("reusable_exec_id") if args.reuse_latest else None
    result: dict[str, object] = {"audit": audit, "cleanup": None, "reusable_exec_id": reusable_exec_id}
    if args.apply:
        result["cleanup"] = service.cleanup_placeholders(
            args.repo_root,
            args.target_branch,
            int(reusable_exec_id) if reusable_exec_id is not None else None,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
