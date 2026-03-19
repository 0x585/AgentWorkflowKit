#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_kit_lib import (
    CURRENT_RELEASE_EXIT,
    INVALID_RELEASE_EXIT,
    check_repo_release,
    workflow_root_from_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether a repository matches the published workflow release.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--repo-id")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_root = workflow_root_from_script(__file__)
    try:
        summary = check_repo_release(
            repo_root=args.repo_root.expanduser().resolve(),
            workflow_root=workflow_root,
            repo_id=args.repo_id,
        )
    except Exception as exc:
        summary = {
            "status": "invalid",
            "error": str(exc),
            "exit_code": INVALID_RELEASE_EXIT,
            "doc_redundancy_warnings": [],
        }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "[workflow-release] status={status} installed={installed} current={current}".format(
                status=summary.get("status"),
                installed=summary.get("installed_version", "-"),
                current=summary.get("current_version", "-"),
            )
        )
    return int(summary.get("exit_code", CURRENT_RELEASE_EXIT))


if __name__ == "__main__":
    raise SystemExit(main())
