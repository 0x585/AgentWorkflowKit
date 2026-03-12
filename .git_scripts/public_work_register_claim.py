#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.2
# Do not edit in this repository.
# Source profile/file id: .git_scripts/public_work_register_claim.py
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".git_scripts" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".git_scripts" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )

if str(REPO_ROOT / "src" / "main" / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src" / "main" / "python"))

from agent_workflow_kit.tooling.service.public_work_register_service import PublicWorkRegisterService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claim or release pending work items in the shared PublicWorkRegister."
    )
    parser.add_argument("--work-id", help="Specific pending work item to claim or release, e.g. W017")
    parser.add_argument("--worker-id", help="Explicit worker identity. Default uses host:branch:worktree:pid:thread")
    parser.add_argument("--ttl-seconds", type=int, default=4 * 60 * 60, help="Lease TTL in seconds for a claim")
    parser.add_argument("--release", action="store_true", help="Release a claimed work item instead of claiming")
    parser.add_argument("--recommend-only", action="store_true", help="Show the next claimable work item without mutating claims")
    parser.add_argument("--force", action="store_true", help="Force release even if current worker is not the owner")
    parser.add_argument("--summary-json", help="Optional path to write summary JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = PublicWorkRegisterService()
    if args.release and args.recommend_only:
      raise SystemExit("--release cannot be combined with --recommend-only")
    if args.recommend_only:
        summary = service.recommend_work_item(repo_root=REPO_ROOT, work_id=args.work_id)
    elif args.release:
        if not args.work_id:
            raise SystemExit("--release requires --work-id")
        summary = service.release_work_item(
            repo_root=REPO_ROOT,
            work_id=args.work_id,
            worker_id=args.worker_id,
            force=args.force,
        )
    else:
        summary = service.claim_work_item(
            repo_root=REPO_ROOT,
            work_id=args.work_id,
            worker_id=args.worker_id,
            ttl_seconds=args.ttl_seconds,
        )
    if args.summary_json:
        output_path = Path(args.summary_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.recommend_only:
        print(
            "[public-work-register] recommended work_id={work_id} register={register}".format(
                work_id=summary.get("recommended_work_id"),
                register=summary["register_markdown_path"],
            )
        )
    else:
        action = "released" if args.release else "claimed"
        work_id = summary.get("released_work_id") if args.release else summary.get("claimed_work_id")
        print(
            f"[public-work-register] {action} work_id={work_id} claim_count={summary['claim_count']} register={summary['register_markdown_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
