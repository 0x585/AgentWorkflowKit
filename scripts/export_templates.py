#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_kit_lib import (
    DEFAULT_PROFILE,
    export_runtime_templates,
    repo_id_for_root,
    workflow_root_from_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export the source repo runtime scripts/hooks back into managed templates."
    )
    parser.add_argument("--repo-id")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_root = workflow_root_from_script(__file__)
    repo_root = args.repo_root.expanduser().resolve() if args.repo_root else workflow_root
    repo_id = args.repo_id or repo_id_for_root(workflow_root, repo_root)
    exported_paths = export_runtime_templates(
        workflow_root=workflow_root,
        repo_id=repo_id,
        profile=args.profile,
    )
    print(
        json.dumps(
            {
                "repo_id": repo_id,
                "repo_root": str(repo_root),
                "profile": args.profile,
                "exported_template_count": len(exported_paths),
                "exported_templates": exported_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
