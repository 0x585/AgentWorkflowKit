#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_kit_lib import (
    DEFAULT_PROFILE,
    apply_release_to_repo,
    workflow_root_from_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply the latest managed workflow release to a repository.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--repo-id")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_root = workflow_root_from_script(__file__)
    summary = apply_release_to_repo(
        workflow_root=workflow_root,
        repo_root=args.repo_root,
        repo_id=args.repo_id,
        profile=args.profile,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
