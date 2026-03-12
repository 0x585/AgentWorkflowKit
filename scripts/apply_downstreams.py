#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_kit_lib import (
    DEFAULT_PROFILE,
    apply_release_to_repo,
    load_current_lock,
    load_current_release,
    load_repo_config,
    prepare_release_artifacts,
    repo_id_for_root,
    repo_ids_from_workflow_root,
    repo_profile,
    workflow_root_from_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply the current managed workflow state from the central repo to downstream repositories."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--include-self", action="store_true")
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
    summaries: list[dict[str, object]] = []

    for repo_id in repo_ids_from_workflow_root(workflow_root):
        if not args.include_self and repo_id == source_repo_id:
            continue
        repo_config = load_repo_config(workflow_root, repo_id)
        if repo_profile(repo_config) != args.profile:
            continue
        summaries.append(
            apply_release_to_repo(
                workflow_root=workflow_root,
                repo_root=Path(str(repo_config["expected_workspace_root"])),
                repo_id=repo_id,
                profile=args.profile,
            )
        )

    print(
        json.dumps(
            {
                "profile": args.profile,
                "source_repo_id": source_repo_id,
                "applied_repo_count": len(summaries),
                "repositories": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
