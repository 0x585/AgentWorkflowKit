#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.30
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/branch_name_policy.py
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
SLUG_LIKE_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
MAX_SUFFIX_LENGTH = 40
AMBIGUOUS_SINGLE_TOKEN_PURPOSES = {
    "help",
    "fix",
    "tmp",
    "temp",
    "misc",
    "test",
    "task",
    "work",
}


@dataclass(frozen=True)
class PolicyViolation(Exception):
    message: str
    hint: str


def _normalized_tokens(text: str) -> list[str]:
    stripped = text.strip()
    if stripped.startswith("codex/"):
        stripped = stripped[len("codex/") :]
    return TOKEN_PATTERN.findall(stripped.lower())


def _strip_codex_prefix(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("codex/"):
        return stripped[len("codex/") :]
    return stripped


def _normalize_slug_candidate(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _truncate_suffix(suffix: str) -> str:
    parts = [part for part in suffix.split("-") if part]
    while len(parts) > 1 and len("-".join(parts)) > MAX_SUFFIX_LENGTH:
        parts.pop()

    truncated = "-".join(parts)
    if len(truncated) > MAX_SUFFIX_LENGTH:
        truncated = truncated[:MAX_SUFFIX_LENGTH].rstrip("-")
    return truncated


def derive_branch_name(text: str) -> str:
    stripped = _strip_codex_prefix(text)
    if not stripped:
        raise PolicyViolation(
            message="Unable to derive a branch name from empty input.",
            hint="Use 2-3 words that describe the task, for example: codex/branch-naming-guard",
        )

    if SLUG_LIKE_PATTERN.fullmatch(stripped):
        suffix = _normalize_slug_candidate(stripped)
    else:
        tokens = _normalized_tokens(stripped)
        if not tokens:
            raise PolicyViolation(
                message="Unable to derive a branch name from the provided input.",
                hint="Use 2-3 words that describe the task, for example: codex/branch-naming-guard",
            )
        suffix = "-".join(tokens[:3])

    suffix = _truncate_suffix(suffix)
    if not suffix:
        raise PolicyViolation(
            message="Unable to derive a descriptive branch purpose from the provided input.",
            hint="Use 2-3 words that describe the task, for example: codex/branch-naming-guard",
        )

    branch_name = f"codex/{suffix}"
    validate_branch_name(branch_name)
    return branch_name


def validate_branch_name(branch_name: str) -> None:
    if not branch_name.startswith("codex/"):
        raise PolicyViolation(
            message=f"Branch name must use the codex/* prefix: {branch_name}",
            hint="Rename it to codex/<descriptive-name> before continuing.",
        )

    suffix = branch_name[len("codex/") :].strip()
    tokens = _normalized_tokens(suffix)
    normalized_suffix = "-".join(tokens)
    if not normalized_suffix:
        raise PolicyViolation(
            message=f"Branch purpose is empty after normalization: {branch_name}",
            hint="Rename it to codex/<descriptive-name> before continuing.",
        )

    if len(tokens) == 1 and normalized_suffix in AMBIGUOUS_SINGLE_TOKEN_PURPOSES:
        raise PolicyViolation(
            message=f"Branch purpose '{normalized_suffix}' is too vague to explain the work intent.",
            hint="Use a descriptive codex/<purpose> name instead.",
        )

    if len(tokens) == 1 and 2 <= len(normalized_suffix) <= 4:
        raise PolicyViolation(
            message=f"Branch purpose '{normalized_suffix}' is too short to be descriptive.",
            hint="Use a descriptive codex/<purpose> name instead.",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Derive and validate descriptive codex branch names.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    derive_parser = subparsers.add_parser("derive", help="Derive a validated codex/* branch name from free-form input")
    derive_parser.add_argument("--input", required=True, help="Free-form branch description or candidate name")

    validate_parser = subparsers.add_parser("validate", help="Validate an existing codex/* branch name")
    validate_parser.add_argument("--branch", required=True, help="Existing branch name to validate")
    validate_parser.add_argument(
        "--context",
        choices=("create", "guard"),
        default="create",
        help="Controls the follow-up hint for invalid branch names",
    )
    return parser


def _print_violation(error: PolicyViolation, *, context: str) -> None:
    print(f"[branch-name-policy] {error.message}", file=sys.stderr)
    if context == "guard":
        print(
            "[branch-name-policy] Rename it before continuing: git branch -m codex/<descriptive-name>",
            file=sys.stderr,
        )
        return
    print(f"[branch-name-policy] {error.hint}", file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "derive":
            print(derive_branch_name(args.input))
            return 0
        if args.command == "validate":
            validate_branch_name(args.branch)
            return 0
    except PolicyViolation as error:
        _print_violation(error, context=getattr(args, "context", "create"))
        return 1
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
