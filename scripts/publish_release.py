#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from workflow_kit_lib import (
    DEFAULT_PROFILE,
    export_runtime_templates,
    repo_id_for_root,
    prepare_release_artifacts,
    workflow_root_from_script,
    write_release_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a managed workflow release.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--version", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_root = workflow_root_from_script(__file__)
    source_repo_id = repo_id_for_root(workflow_root, workflow_root)
    export_runtime_templates(
        workflow_root=workflow_root,
        repo_id=source_repo_id,
        profile=args.profile,
    )
    release_payload, lock_payload = prepare_release_artifacts(
        workflow_root=workflow_root,
        profile=args.profile,
        version=args.version,
    )
    manifest_hash = str(release_payload["release_manifest_hash"])
    write_release_artifacts(
        workflow_root=workflow_root,
        profile=args.profile,
        version=args.version,
        release_payload=release_payload,
        lock_payload=lock_payload,
    )
    print(json.dumps({"profile": args.profile, "workflow_version": args.version, "release_manifest_hash": manifest_hash}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
