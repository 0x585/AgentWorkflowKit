from __future__ import annotations

import fcntl
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


class PublicWorkRegisterService:
    DEFAULT_REGISTER_ROOT = Path("/Users/pi/PyCharmProject/PublicWorkRegister")
    ENV_KEY = "AGENT_WORKFLOW_KIT_PUBLIC_WORK_REGISTER_ROOT"
    LOCK_TTL_SECONDS = 4 * 60 * 60

    def sync_pending_worklist(
        self,
        repo_root: Path,
        released_work_ids: list[str] | None = None,
    ) -> JsonObject:
        pending_items = self._parse_pending_worklist(repo_root)
        return self._mutate_state(
            repo_root=repo_root,
            pending_items=pending_items,
            released_work_ids=released_work_ids or [],
        )

    def claim_work_item(
        self,
        repo_root: Path,
        work_id: str | None = None,
        worker_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> JsonObject:
        pending_items = self._parse_pending_worklist(repo_root)
        ttl = ttl_seconds if ttl_seconds and ttl_seconds > 0 else self.LOCK_TTL_SECONDS
        now_ms = self._now_ms()
        selected_worker = worker_id or self.build_worker_identity(repo_root)

        def mutate(state: JsonObject) -> JsonObject:
            claims = self._normalize_claims(state.get("claims"))
            claims = self._prune_claims(claims, pending_items, [], now_ms)
            selected_item = self._select_claim_candidate(pending_items, claims, work_id)
            if selected_item is None:
                raise RuntimeError("no claimable pending work item found")
            active_claim = claims.get(selected_item["work_id"])
            if active_claim and active_claim.get("worker_id") != selected_worker:
                raise RuntimeError(
                    f"pending work item {selected_item['work_id']} is already claimed by {active_claim.get('worker_id')}"
                )
            branch_name = self._current_branch(repo_root)
            claims[selected_item["work_id"]] = {
                "work_id": selected_item["work_id"],
                "worker_id": selected_worker,
                "branch": branch_name,
                "worktree_path": str(repo_root),
                "claimed_at_ms": now_ms,
                "lease_until_ms": now_ms + ttl * 1000,
                "thread_name": threading.current_thread().name,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
            }
            state["claims"] = claims
            summary = self._finalize_state(repo_root, state, pending_items, now_ms)
            summary["selected_work_id"] = selected_item["work_id"]
            return summary

        summary = self._locked_state_apply(repo_root, mutate)
        summary["claimed_work_id"] = summary.get("selected_work_id")
        return summary

    def recommend_work_item(
        self,
        repo_root: Path,
        work_id: str | None = None,
    ) -> JsonObject:
        pending_items = self._parse_pending_worklist(repo_root)
        now_ms = self._now_ms()

        def mutate(state: JsonObject) -> JsonObject:
            claims = self._normalize_claims(state.get("claims"))
            claims = self._prune_claims(claims, pending_items, [], now_ms)
            state["claims"] = claims
            summary = self._finalize_state(repo_root, state, pending_items, now_ms)
            recommendation = self._recommend_claim_candidate(pending_items, claims, work_id)
            summary.update(recommendation)
            return summary

        return self._locked_state_apply(repo_root, mutate)

    def release_work_item(
        self,
        repo_root: Path,
        work_id: str,
        worker_id: str | None = None,
        force: bool = False,
    ) -> JsonObject:
        pending_items = self._parse_pending_worklist(repo_root)
        selected_worker = worker_id or self.build_worker_identity(repo_root)
        now_ms = self._now_ms()

        def mutate(state: JsonObject) -> JsonObject:
            claims = self._normalize_claims(state.get("claims"))
            claims = self._prune_claims(claims, pending_items, [], now_ms)
            active_claim = claims.get(work_id)
            if active_claim is None:
                state["claims"] = claims
                summary = self._finalize_state(repo_root, state, pending_items, now_ms)
                summary["released_work_id"] = work_id
                summary["release_state"] = "NOT_FOUND"
                return summary
            if not force and active_claim.get("worker_id") != selected_worker:
                raise RuntimeError(
                    f"pending work item {work_id} is claimed by {active_claim.get('worker_id')}, not {selected_worker}"
                )
            claims.pop(work_id, None)
            state["claims"] = claims
            summary = self._finalize_state(repo_root, state, pending_items, now_ms)
            summary["released_work_id"] = work_id
            summary["release_state"] = "RELEASED"
            return summary

        return self._locked_state_apply(repo_root, mutate)

    def build_worker_identity(self, repo_root: Path) -> str:
        branch_name = self._current_branch(repo_root)
        return ":".join(
            [
                socket.gethostname(),
                branch_name,
                repo_root.name,
                str(os.getpid()),
                threading.current_thread().name,
            ]
        )

    def _locked_state_apply(self, repo_root: Path, mutate) -> JsonObject:
        register_root = self._resolve_register_root(repo_root)
        register_root.mkdir(parents=True, exist_ok=True)
        lock_path = register_root / ".pending-work-register.lock"
        state_path = register_root / ".pending-work-register.state.json"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._load_state(state_path)
            summary = mutate(state)
            if "register_root" not in summary:
                summary["register_root"] = str(register_root)
            return summary

    def _mutate_state(
        self,
        repo_root: Path,
        pending_items: list[JsonObject],
        released_work_ids: list[str],
    ) -> JsonObject:
        now_ms = self._now_ms()

        def mutate(state: JsonObject) -> JsonObject:
            claims = self._normalize_claims(state.get("claims"))
            claims = self._prune_claims(claims, pending_items, released_work_ids, now_ms)
            state["claims"] = claims
            return self._finalize_state(repo_root, state, pending_items, now_ms)

        return self._locked_state_apply(repo_root, mutate)

    def _finalize_state(
        self,
        repo_root: Path,
        state: JsonObject,
        pending_items: list[JsonObject],
        now_ms: int,
    ) -> JsonObject:
        register_root = self._resolve_register_root(repo_root)
        project_name = self._resolve_project_dir_name(repo_root)
        register_root.mkdir(parents=True, exist_ok=True)
        state_path = register_root / ".pending-work-register.state.json"
        markdown_path = register_root / "pending-work-register.md"
        claims = self._normalize_claims(state.get("claims"))
        state["version"] = 1
        state["source_repo_root"] = str(repo_root)
        state["source_pending_worklist"] = str(repo_root / "docs" / "design" / "pending-worklist.md")
        state["project_name"] = project_name
        state["synced_at_ms"] = now_ms
        state["pending_items"] = pending_items
        state["claims"] = claims
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(
            self._render_markdown(repo_root, pending_items, claims, now_ms),
            encoding="utf-8",
        )
        return {
            "register_root": str(register_root),
            "register_markdown_path": str(markdown_path),
            "register_state_path": str(state_path),
            "pending_count": len(pending_items),
            "claim_count": len(claims),
            "pending_items": pending_items,
            "claims": list(claims.values()),
            "synced_at_ms": now_ms,
        }

    def _parse_pending_worklist(self, repo_root: Path) -> list[JsonObject]:
        pending_path = repo_root / "docs" / "design" / "pending-worklist.md"
        if not pending_path.is_file():
            raise RuntimeError(f"pending worklist not found: {pending_path}")
        items: list[JsonObject] = []
        for raw_line in pending_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line.startswith("| W"):
                continue
            columns = [column.strip() for column in line.strip("|").split("|")]
            if len(columns) < 6:
                continue
            work_id, priority, decision, status, title, description = columns[:6]
            items.append(
                {
                    "work_id": work_id,
                    "priority": priority,
                    "decision": decision,
                    "status": status,
                    "title": title,
                    "description": description,
                }
            )
        return items

    def _normalize_claims(self, raw_claims: object) -> JsonObject:
        if not isinstance(raw_claims, dict):
            return {}
        normalized: JsonObject = {}
        for work_id, raw_claim in raw_claims.items():
            if not isinstance(work_id, str) or not isinstance(raw_claim, dict):
                continue
            normalized[work_id] = dict(raw_claim)
        return normalized

    def _prune_claims(
        self,
        claims: JsonObject,
        pending_items: list[JsonObject],
        released_work_ids: list[str],
        now_ms: int,
    ) -> JsonObject:
        pending_ids = {str(item.get("work_id")) for item in pending_items}
        released_ids = set(released_work_ids)
        pruned: JsonObject = {}
        for work_id, claim in claims.items():
            if work_id not in pending_ids:
                continue
            if work_id in released_ids:
                continue
            lease_until = self._as_int(claim.get("lease_until_ms"))
            if lease_until is not None and lease_until < now_ms:
                continue
            pruned[work_id] = claim
        return pruned

    def _select_claim_candidate(
        self,
        pending_items: list[JsonObject],
        claims: JsonObject,
        work_id: str | None,
    ) -> JsonObject | None:
        if work_id:
            for item in pending_items:
                if str(item.get("work_id")) != work_id:
                    continue
                if self._is_claimable(item):
                    return item
                raise RuntimeError(f"pending work item {work_id} is not claimable")
            raise RuntimeError(f"pending work item {work_id} not found")

        for item in pending_items:
            if not self._is_claimable(item):
                continue
            if str(item.get("work_id")) in claims:
                continue
            return item
        return None

    def _recommend_claim_candidate(
        self,
        pending_items: list[JsonObject],
        claims: JsonObject,
        work_id: str | None,
    ) -> JsonObject:
        recommended_item = self._select_claim_candidate(pending_items, claims, None)
        skipped_claimed_work_ids = self._collect_skipped_claimed_work_ids(pending_items, claims)
        summary: JsonObject = {
            "recommended_work_id": None,
            "recommended_work_item": None,
            "requested_work_claimable": True,
            "skipped_claimed_work_ids": skipped_claimed_work_ids,
            "requested_work_claimed_by": None,
            "requested_work_id": work_id,
            "requested_work_locked": False,
        }
        if work_id is None:
            if recommended_item is not None:
                summary["recommended_work_id"] = str(recommended_item.get("work_id"))
                summary["recommended_work_item"] = dict(recommended_item)
            return summary

        requested_item = self._find_pending_item(pending_items, work_id)
        if requested_item is None:
            raise RuntimeError(f"pending work item {work_id} not found")
        requested_claim = claims.get(work_id)
        if not self._is_claimable(requested_item):
            summary["requested_work_claimable"] = False
            if requested_claim is not None:
                summary["requested_work_locked"] = True
                summary["requested_work_claimed_by"] = str(requested_claim.get("worker_id", ""))
            if recommended_item is not None:
                summary["recommended_work_id"] = str(recommended_item.get("work_id"))
                summary["recommended_work_item"] = dict(recommended_item)
            return summary
        if requested_claim is None:
            summary["recommended_work_id"] = work_id
            summary["recommended_work_item"] = dict(requested_item)
            return summary

        summary["requested_work_locked"] = True
        summary["requested_work_claimed_by"] = str(requested_claim.get("worker_id", ""))
        if recommended_item is not None:
            summary["recommended_work_id"] = str(recommended_item.get("work_id"))
            summary["recommended_work_item"] = dict(recommended_item)
        return summary

    def _is_claimable(self, item: JsonObject) -> bool:
        return str(item.get("decision")) == "EXECUTE" and str(item.get("status")) != "BLOCKED"

    def _find_pending_item(self, pending_items: list[JsonObject], work_id: str) -> JsonObject | None:
        for item in pending_items:
            if str(item.get("work_id")) == work_id:
                return item
        return None

    def _collect_skipped_claimed_work_ids(
        self,
        pending_items: list[JsonObject],
        claims: JsonObject,
    ) -> list[str]:
        skipped: list[str] = []
        for item in pending_items:
            work_id = str(item.get("work_id"))
            if not self._is_claimable(item):
                continue
            if work_id not in claims:
                break
            skipped.append(work_id)
        return skipped

    def _load_state(self, state_path: Path) -> JsonObject:
        if not state_path.is_file():
            return {}
        text = state_path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        raw = json.loads(text)
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    def _render_markdown(
        self,
        repo_root: Path,
        pending_items: list[JsonObject],
        claims: JsonObject,
        now_ms: int,
    ) -> str:
        project_name = self._resolve_project_dir_name(repo_root)
        lines: list[str] = [
            "# Public Work Register",
            "",
            f"- Project: `{project_name}`",
            f"- Source repo: `{repo_root}`",
            f"- Synced at(ms): `{now_ms}`",
            f"- Total pending items: `{len(pending_items)}`",
            f"- Active claims: `{len(claims)}`",
            "",
            "## Active Claims",
            "",
        ]
        if claims:
            lines.extend(
                [
                    "| Work ID | Worker | Branch | Worktree | Lease Until(ms) |",
                    "|---|---|---|---|---|",
                ]
            )
            for work_id in sorted(claims):
                claim = claims[work_id]
                lines.append(
                    "| {work_id} | {worker} | {branch} | {worktree} | {lease_until} |".format(
                        work_id=work_id,
                        worker=str(claim.get("worker_id", "")),
                        branch=str(claim.get("branch", "")),
                        worktree=str(claim.get("worktree_path", "")),
                        lease_until=str(claim.get("lease_until_ms", "")),
                    )
                )
        else:
            lines.append("- 无")
        lines.extend(["", "## Pending Items", ""])
        if pending_items:
            lines.extend(
                [
                    "| Work ID | Priority | Decision | Status | 工作项 | 占用状态 | 占用者 | 说明 |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            for item in pending_items:
                work_id = str(item.get("work_id"))
                claim = claims.get(work_id)
                lines.append(
                    "| {work_id} | {priority} | {decision} | {status} | {title} | {occupied} | {worker} | {description} |".format(
                        work_id=work_id,
                        priority=str(item.get("priority", "")),
                        decision=str(item.get("decision", "")),
                        status=str(item.get("status", "")),
                        title=str(item.get("title", "")),
                        occupied="LOCKED" if claim else "FREE",
                        worker=str(claim.get("worker_id", "")) if claim else "",
                        description=str(item.get("description", "")),
                    )
                )
        else:
            lines.append("- 无")
        lines.append("")
        return "\n".join(lines)

    def _resolve_register_root(self, repo_root: Path) -> Path:
        override = os.environ.get(self.ENV_KEY, "").strip()
        if override:
            return Path(override).expanduser().resolve()
        project_dir_name = self._resolve_project_dir_name(repo_root)
        return (self.DEFAULT_REGISTER_ROOT / project_dir_name).resolve()

    def _resolve_project_dir_name(self, repo_root: Path) -> str:
        common_dir = self._resolve_git_common_dir(repo_root)
        if common_dir is not None:
            project_root = common_dir.parent
            if project_root.name:
                return str(project_root.name)
        resolved_repo_root = repo_root.expanduser().resolve()
        if resolved_repo_root.name:
            return str(resolved_repo_root.name)
        return str(repo_root.name or "repo")

    def _resolve_git_common_dir(self, repo_root: Path) -> Path | None:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            common_dir_text = result.stdout.strip()
            if not common_dir_text:
                return None
            return Path(common_dir_text).expanduser().resolve()
        except Exception:
            return None

    def _current_branch(self, repo_root: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), "branch", "--show-current"],
                check=True,
                capture_output=True,
                text=True,
            )
            branch_name = result.stdout.strip()
            return branch_name or "unknown"
        except Exception:
            return "unknown"

    def _as_int(self, value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _now_ms(self) -> int:
        return int(time.time() * 1000)
