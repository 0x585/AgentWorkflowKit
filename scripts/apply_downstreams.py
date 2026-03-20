#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_kit_lib import (
    DEFAULT_PROFILE,
    load_current_lock,
    load_current_release,
    load_repo_config,
    prepare_release_artifacts,
    repo_id_for_root,
    repo_ids_from_workflow_root,
    repo_profile,
    submit_release_to_repo_via_worktree_commit,
    workflow_root_from_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create local downstream worktree commits for repositories that need the current managed workflow release."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--repo-id", action="append", dest="repo_ids")
    parser.add_argument("--resume-existing-worktree", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_root = workflow_root_from_script(__file__)
    source_repo_id = repo_id_for_root(workflow_root, workflow_root)
    current_release = load_current_release(workflow_root, args.profile)
    current_version = str(current_release["workflow_version"])
    expected_release, expected_lock = prepare_release_artifacts(
        workflow_root=workflow_root,
        profile=args.profile,
        version=current_version,
    )
    current_lock = load_current_lock(workflow_root, args.profile)
    if current_release != expected_release or current_lock != expected_lock:
        raise SystemExit(
            "Current release artifacts are stale. Publish a new release before applying downstream repositories."
        )
    available_repo_ids = repo_ids_from_workflow_root(workflow_root)
    selected_repo_ids = set(args.repo_ids or [])
    unknown_repo_ids = sorted(selected_repo_ids - set(available_repo_ids))
    if unknown_repo_ids:
        raise SystemExit(f"Unknown repo ids: {', '.join(unknown_repo_ids)}")
    summaries: list[dict[str, object]] = []
    failed_repo_count = 0

    for repo_id in available_repo_ids:
        if not args.include_self and repo_id == source_repo_id:
            continue
        if selected_repo_ids and repo_id not in selected_repo_ids:
            continue
        repo_config = load_repo_config(workflow_root, repo_id)
        if repo_profile(repo_config) != args.profile:
            continue
        summary = submit_release_to_repo_via_worktree_commit(
            workflow_root=workflow_root,
            repo_root=Path(str(repo_config["expected_workspace_root"])),
            repo_id=repo_id,
            profile=args.profile,
            resume_existing_worktree=args.resume_existing_worktree,
            auto_release_after_review=True,
        )
        summaries.append(summary)
        if summary.get("action") not in {"released", "skip-current", "noop-cleanup"}:
            failed_repo_count += 1

    print(
        json.dumps(
            {
                "profile": args.profile,
                "source_repo_id": source_repo_id,
                "processed_repo_count": len(summaries),
                "failed_repo_count": failed_repo_count,
                "repositories": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failed_repo_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
