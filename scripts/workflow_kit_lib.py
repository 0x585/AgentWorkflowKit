from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = "full_codex_flow"
MANAGED_WORKFLOW_DIR = ".workflow-kit"
COMPAT_MANAGED_GIT_SCRIPTS_DIR = ".git_scripts"
MANAGED_RUNTIME_DIRS = (
    MANAGED_WORKFLOW_DIR,
    COMPAT_MANAGED_GIT_SCRIPTS_DIR,
)
MANAGED_HOOKS_DIR = ".githooks"
MANAGED_RUNTIME_BASENAMES = (
    "workflow_guard.sh",
    "assert_workspace.sh",
    "setup_githooks.sh",
    "git_default_branch.sh",
    "new_branch.sh",
    "new_worktree.sh",
    "ensure_shared_venv.sh",
    "new_exec.sh",
    "session_sync.sh",
    "session_sync_status.sh",
    "session_push_autorelease.sh",
    "session_release_resume.sh",
    "public_work_register_sync.py",
    "public_work_register_claim.py",
    "exec_record_hygiene.py",
    "pending_worklist_autoclean.py",
)
SHARED_VENV_NAMES = (
    ".venv314",
    ".venv313",
    ".venv312",
    ".venv311",
    ".venv310",
    ".venv",
)
WORKFLOW_EXCLUDE_MARKER_START = "# workflow-kit managed excludes start"
WORKFLOW_EXCLUDE_MARKER_END = "# workflow-kit managed excludes end"
DOWNSTREAM_EXCLUDE_PATTERNS = tuple(f"/{name}" for name in SHARED_VENV_NAMES)
MANAGED_DOC_MARKERS = {
    "AGENTS.md": ("<!-- workflow-kit:agents:start -->", "<!-- workflow-kit:agents:end -->"),
    "README.md": ("<!-- workflow-kit:readme:start -->", "<!-- workflow-kit:readme:end -->"),
}
LEGACY_AGENTS_WORKFLOW_SECTION_TITLES = {
    "Workspace Guard",
    "Session Start Default",
    "Git Hooks Enable",
    "Session End Default",
    "Code Edit Guard",
    "Execution Confirmation Policy",
    "Disallowed States",
    "Recommended Workflow",
    "Branch Policy",
    "Commit Policy",
}
CURRENT_RELEASE_EXIT = 0
OUTDATED_RELEASE_EXIT = 10
DRIFT_RELEASE_EXIT = 20
INVALID_RELEASE_EXIT = 30


@dataclass(frozen=True)
class ManagedEntry:
    entry_type: str
    output: str
    template: str
    executable: bool = False
    start_marker: str | None = None
    end_marker: str | None = None


def workflow_root_from_script(script_file: str | Path) -> Path:
    return Path(script_file).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_required_json(path: Path, missing_message: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{missing_message}: {path}")
    return load_json(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_repo_config(workflow_root: Path, repo_id: str) -> dict[str, Any]:
    path = workflow_root / "repos" / f"{repo_id}.json"
    payload = load_required_json(path, "repo config not found")
    payload.setdefault("repo_id", repo_id)
    return payload


def load_profile_manifest(workflow_root: Path, profile: str) -> dict[str, Any]:
    path = workflow_root / "profiles" / profile / "profile.json"
    return load_required_json(path, "profile manifest not found")


def repo_profile(repo_config: dict[str, Any], default: str = DEFAULT_PROFILE) -> str:
    return str(repo_config.get("profile", default))


def managed_entries_from_manifest(profile_manifest: dict[str, Any]) -> list[ManagedEntry]:
    entries: list[ManagedEntry] = []
    for raw_entry in profile_manifest.get("managed_entries", []):
        entries.append(
            ManagedEntry(
                entry_type=str(raw_entry["type"]),
                output=str(raw_entry["output"]),
                template=str(raw_entry["template"]),
                executable=bool(raw_entry.get("executable", False)),
                start_marker=raw_entry.get("start_marker"),
                end_marker=raw_entry.get("end_marker"),
            )
        )
    return entries


def render_template_text(template_text: str, context: dict[str, Any]) -> str:
    rendered = template_text
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", str(value))
    unresolved = re.findall(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}", rendered)
    if unresolved:
        raise RuntimeError("template rendering left unresolved placeholders")
    return rendered


def render_template_path(
    workflow_root: Path,
    template_path: str,
    context: dict[str, Any],
) -> str:
    template = (workflow_root / template_path).read_text(encoding="utf-8")
    return render_template_text(template, context)


def release_json_path(workflow_root: Path, profile: str) -> Path:
    return workflow_root / "profiles" / profile / "release.json"


def lock_json_path(workflow_root: Path, profile: str) -> Path:
    return workflow_root / "profiles" / profile / "managed-files.lock.json"


def release_history_dir(workflow_root: Path, profile: str, version: str) -> Path:
    return workflow_root / "profiles" / profile / "releases" / version


def build_release_payload(profile: str, version: str, repo_ids: list[str]) -> dict[str, Any]:
    return {
        "profile": profile,
        "workflow_version": version,
        "repositories": sorted(repo_ids),
    }


def release_manifest_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    return sha256_bytes(serialized)


def build_context(
    workflow_root: Path,
    repo_root: Path,
    repo_config: dict[str, Any],
    workflow_version: str,
    release_hash: str,
    managed_entry: ManagedEntry,
) -> dict[str, Any]:
    profile = repo_profile(repo_config)
    repo_id = str(repo_config["repo_id"])
    workflow_repo_root = canonical_workflow_repo_root(workflow_root)
    python_package_name = str(repo_config["python_package_name"])
    env_prefix = python_package_name.upper().replace(".", "_").replace("-", "_")
    return {
        "workflow_repo_root": str(workflow_repo_root),
        "workflow_version": workflow_version,
        "profile": profile,
        "release_manifest_hash": release_hash,
        "repo_id": repo_id,
        "repo_root": str(repo_root),
        "repo_name": repo_root.name,
        "expected_workspace_root": str(repo_config["expected_workspace_root"]),
        "default_branch": str(repo_config["default_branch"]),
        "python_package_name": python_package_name,
        "public_work_register_env_key": f"{env_prefix}_PUBLIC_WORK_REGISTER_ROOT",
        "compile_main_path": str(repo_config["compile_main_path"]),
        "compile_test_path": str(repo_config["compile_test_path"]),
        "public_work_register_dir": str(repo_config["public_work_register_dir"]),
        "managed_entry_id": managed_entry.output,
        "managed_template_path": managed_entry.template,
    }


def canonical_workflow_repo_root(workflow_root: Path) -> Path:
    source_path = workflow_root / ".workflow-kit" / "source.json"
    if source_path.is_file():
        payload = load_json(source_path)
        candidate = payload.get("workflow_repo_root") or payload.get("source_repo_root")
        if candidate:
            candidate_path = Path(str(candidate)).expanduser().resolve()
            if candidate_path.is_dir():
                return candidate_path
    return workflow_root.resolve()


def inject_block(original: str, start_marker: str, end_marker: str, managed_text: str) -> str:
    managed_payload = f"{start_marker}\n{managed_text.rstrip()}\n{end_marker}\n"
    if start_marker in original and end_marker in original:
        before, remainder = original.split(start_marker, 1)
        _, after = remainder.split(end_marker, 1)
        prefix = before.rstrip("\n")
        suffix = after.lstrip("\n")
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(managed_payload.rstrip("\n"))
        if suffix:
            parts.append(suffix)
        return "\n\n".join(parts).rstrip("\n") + "\n"
    base = original.rstrip("\n")
    if base:
        return base + "\n\n" + managed_payload
    return managed_payload


def extract_block(text: str, start_marker: str, end_marker: str) -> str | None:
    if start_marker not in text or end_marker not in text:
        return None
    _, remainder = text.split(start_marker, 1)
    content, _ = remainder.split(end_marker, 1)
    return content.strip("\n") + "\n"


def render_entry(
    workflow_root: Path,
    repo_root: Path,
    repo_config: dict[str, Any],
    workflow_version: str,
    release_hash: str,
    entry: ManagedEntry,
) -> dict[str, Any]:
    context = build_context(
        workflow_root=workflow_root,
        repo_root=repo_root,
        repo_config=repo_config,
        workflow_version=workflow_version,
        release_hash=release_hash,
        managed_entry=entry,
    )
    rendered = render_template_path(workflow_root, entry.template, context)
    rendered_output = render_template_text(entry.output, context)
    payload = {
        "type": entry.entry_type,
        "path": rendered_output,
        "sha256": sha256_text(rendered),
        "content": rendered,
    }
    if entry.entry_type == "block":
        payload["start_marker"] = entry.start_marker
        payload["end_marker"] = entry.end_marker
    if entry.executable:
        payload["executable"] = True
    return payload


def render_repo_entries(
    workflow_root: Path,
    repo_root: Path,
    repo_config: dict[str, Any],
    workflow_version: str,
    release_hash: str,
) -> list[dict[str, Any]]:
    profile_manifest = load_profile_manifest(workflow_root, repo_profile(repo_config))
    return [
        render_entry(
            workflow_root=workflow_root,
            repo_root=repo_root,
            repo_config=repo_config,
            workflow_version=workflow_version,
            release_hash=release_hash,
            entry=entry,
        )
        for entry in managed_entries_from_manifest(profile_manifest)
    ]


def apply_rendered_entries(repo_root: Path, rendered_entries: list[dict[str, Any]]) -> None:
    for entry in rendered_entries:
        target = repo_root / str(entry["path"])
        if entry["type"] == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(entry["content"]), encoding="utf-8")
            if entry.get("executable"):
                target.chmod(0o755)
            continue
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        updated = inject_block(
            original=original,
            start_marker=str(entry["start_marker"]),
            end_marker=str(entry["end_marker"]),
            managed_text=str(entry["content"]),
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding="utf-8")


def git_info_exclude_path(repo_root: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def ensure_local_exclude_patterns(repo_root: Path, patterns: tuple[str, ...] = DOWNSTREAM_EXCLUDE_PATTERNS) -> None:
    exclude_path = git_info_exclude_path(repo_root)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    prefix = existing
    suffix = ""
    if WORKFLOW_EXCLUDE_MARKER_START in existing and WORKFLOW_EXCLUDE_MARKER_END in existing:
        prefix, remainder = existing.split(WORKFLOW_EXCLUDE_MARKER_START, 1)
        _, suffix = remainder.split(WORKFLOW_EXCLUDE_MARKER_END, 1)

    updated = prefix.rstrip("\n")
    if patterns:
        managed_block = (
            f"{WORKFLOW_EXCLUDE_MARKER_START}\n"
            + "\n".join(patterns)
            + f"\n{WORKFLOW_EXCLUDE_MARKER_END}\n"
        )
        if updated:
            updated += "\n\n"
        updated += managed_block.rstrip("\n")
    suffix = suffix.lstrip("\n")
    if suffix:
        if updated:
            updated += "\n\n"
        updated += suffix.rstrip("\n")
    if updated:
        updated += "\n"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_path.write_text(updated, encoding="utf-8")


def ensure_core_hooks_path(repo_root: Path, hooks_path: str = MANAGED_HOOKS_DIR) -> None:
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "core.hooksPath", hooks_path],
        check=True,
        capture_output=True,
        text=True,
    )


def remove_legacy_managed_runtime_files(repo_root: Path) -> list[str]:
    return []


def _compat_shell_wrapper(target_dir: str, basename: str) -> str:
    return (
        "#!/usr/bin/env bash\n\n"
        "set -euo pipefail\n\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
        f'exec "$ROOT/{target_dir}/{basename}" "$@"\n'
    )


def _compat_python_wrapper(target_dir: str, basename: str) -> str:
    return (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        f'TARGET = ROOT / "{target_dir}" / "{basename}"\n'
        'os.execv(str(TARGET), [str(TARGET), *sys.argv[1:]])\n'
    )


def refresh_script_wrappers(repo_root: Path, target_dir: str = MANAGED_WORKFLOW_DIR) -> list[str]:
    refreshed_paths: list[str] = []
    scripts_dir = repo_root / "scripts"
    for basename in MANAGED_RUNTIME_BASENAMES:
        wrapper_path = scripts_dir / basename
        if not wrapper_path.exists():
            continue
        if basename.endswith(".py"):
            wrapper_text = _compat_python_wrapper(target_dir, basename)
        else:
            wrapper_text = _compat_shell_wrapper(target_dir, basename)
        if wrapper_path.read_text(encoding="utf-8") != wrapper_text:
            wrapper_path.write_text(wrapper_text, encoding="utf-8")
        wrapper_path.chmod(0o755)
        refreshed_paths.append(str(wrapper_path))
    return refreshed_paths


def refresh_workflow_doc_entrypoints(repo_root: Path) -> list[str]:
    refreshed_paths: list[str] = []
    for relative_path, markers in MANAGED_DOC_MARKERS.items():
        target_path = repo_root / relative_path
        if not target_path.is_file():
            continue
        original = target_path.read_text(encoding="utf-8")
        start_marker, end_marker = markers
        if start_marker in original and end_marker in original:
            before, remainder = original.split(start_marker, 1)
            managed, after = remainder.split(end_marker, 1)
            updated = (
                before.replace(".git_scripts", MANAGED_WORKFLOW_DIR)
                + start_marker
                + managed
                + end_marker
                + after.replace(".git_scripts", MANAGED_WORKFLOW_DIR)
            )
        else:
            updated = original.replace(".git_scripts", MANAGED_WORKFLOW_DIR)
        if relative_path == "AGENTS.md":
            updated = _strip_legacy_agents_workflow_sections(updated)
        if updated != original:
            target_path.write_text(updated, encoding="utf-8")
            refreshed_paths.append(str(target_path))
    return refreshed_paths


def _strip_legacy_agents_workflow_sections(text: str) -> str:
    start_marker = MANAGED_DOC_MARKERS["AGENTS.md"][0]
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(##)\s+(.+?)\s*$", line.rstrip("\n"))
        if match:
            title = re.sub(r"\s+\(Mandatory\)$", "", match.group(2)).strip()
            if title in LEGACY_AGENTS_WORKFLOW_SECTION_TITLES:
                index += 1
                while index < len(lines):
                    next_line = lines[index]
                    if next_line.rstrip("\n") == start_marker:
                        break
                    next_match = re.match(r"^(##)\s+(.+?)\s*$", next_line.rstrip("\n"))
                    if next_match:
                        break
                    index += 1
                continue
        kept.append(line)
        index += 1
    updated = "".join(kept)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.strip() + "\n"


def repo_ids_from_workflow_root(workflow_root: Path) -> list[str]:
    repo_dir = workflow_root / "repos"
    return sorted(path.stem for path in repo_dir.glob("*.json"))


def repo_id_from_source_metadata(repo_root: Path) -> str | None:
    source_path = repo_root / ".workflow-kit" / "source.json"
    if not source_path.is_file():
        return None
    repo_id = load_json(source_path).get("repo_id")
    if repo_id is None:
        return None
    return str(repo_id)


def repo_id_for_root(workflow_root: Path, repo_root: Path) -> str:
    resolved_root = repo_root.resolve()
    metadata_repo_id = repo_id_from_source_metadata(resolved_root)
    if metadata_repo_id:
        load_repo_config(workflow_root, metadata_repo_id)
        return metadata_repo_id
    matches: list[str] = []
    for repo_id in repo_ids_from_workflow_root(workflow_root):
        repo_config = load_repo_config(workflow_root, repo_id)
        expected_root = Path(str(repo_config["expected_workspace_root"])).resolve()
        if expected_root == resolved_root:
            matches.append(repo_id)
    if not matches:
        raise FileNotFoundError(f"repo config not found for root: {resolved_root}")
    if len(matches) > 1:
        raise RuntimeError(f"multiple repo configs match root {resolved_root}: {matches}")
    return matches[0]


def build_lock_manifest(
    workflow_root: Path,
    profile: str,
    version: str,
    release_hash: str,
) -> dict[str, Any]:
    repositories: dict[str, Any] = {}
    for repo_id in repo_ids_from_workflow_root(workflow_root):
        repo_config = load_repo_config(workflow_root, repo_id)
        if repo_profile(repo_config) != profile:
            continue
        repo_root = Path(str(repo_config["expected_workspace_root"]))
        entries = render_repo_entries(
            workflow_root=workflow_root,
            repo_root=repo_root,
            repo_config=repo_config,
            workflow_version=version,
            release_hash=release_hash,
        )
        repositories[repo_id] = {"entries": entries}
    return {
        "profile": profile,
        "workflow_version": version,
        "release_manifest_hash": release_hash,
        "repositories": repositories,
    }


def prepare_release_artifacts(
    workflow_root: Path,
    profile: str,
    version: str,
    repo_ids: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_repo_ids = repo_ids_from_workflow_root(workflow_root) if repo_ids is None else sorted(repo_ids)
    release_payload = build_release_payload(profile, version, resolved_repo_ids)
    manifest_hash = release_manifest_hash(release_payload)
    lock_payload = build_lock_manifest(
        workflow_root=workflow_root,
        profile=profile,
        version=version,
        release_hash=manifest_hash,
    )
    release_payload["release_manifest_hash"] = manifest_hash
    return release_payload, lock_payload


def managed_runtime_entries(workflow_root: Path, profile: str) -> list[ManagedEntry]:
    profile_manifest = load_profile_manifest(workflow_root, profile)
    return [
        entry
        for entry in managed_entries_from_manifest(profile_manifest)
        if entry.entry_type == "file"
        and (
            entry.output.startswith(f"{MANAGED_HOOKS_DIR}/")
            or any(entry.output.startswith(f"{runtime_dir}/") for runtime_dir in MANAGED_RUNTIME_DIRS)
        )
    ]


def placeholderize_runtime_entry(
    source_text: str,
    repo_config: dict[str, Any],
    entry: ManagedEntry,
) -> str:
    placeholderized = re.sub(
        r"(?m)^# Workflow-Version: .+$",
        "# Workflow-Version: {{ workflow_version }}",
        source_text,
    )
    placeholderized = re.sub(
        r"(?m)^# Source profile/file id: .+$",
        "# Source profile/file id: {{ managed_entry_id }}",
        placeholderized,
    )

    expected_root = str(repo_config["expected_workspace_root"])
    default_branch = str(repo_config["default_branch"])
    python_package_name = str(repo_config["python_package_name"])
    compile_main_path = str(repo_config["compile_main_path"])
    compile_test_path = str(repo_config["compile_test_path"])

    replacements = [
        (
            f'PREFERRED_BRANCH="{default_branch}"',
            'PREFERRED_BRANCH="{{ default_branch }}"',
        ),
        (
            f'EXPECTED_ROOT="${{EXPECTED_WORKSPACE_ROOT:-{expected_root}}}"',
            'EXPECTED_ROOT="${EXPECTED_WORKSPACE_ROOT:-{{ expected_workspace_root }}}"',
        ),
        (
            f'DEFAULT_BRANCH="$("$ROOT/{MANAGED_WORKFLOW_DIR}/git_default_branch.sh" "$EXPECTED_ROOT" 2>/dev/null || echo {default_branch})"',
            f'DEFAULT_BRANCH="$("$ROOT/{MANAGED_WORKFLOW_DIR}/git_default_branch.sh" "$EXPECTED_ROOT" 2>/dev/null || echo {{{{ default_branch }}}})"',
        ),
        (f'echo "{default_branch}"', 'echo "{{ default_branch }}"'),
        (
            f'from {python_package_name}.tooling.service.public_work_register_service import PublicWorkRegisterService',
            "from {{ python_package_name }}.tooling.service.public_work_register_service import PublicWorkRegisterService",
        ),
        (
            f'if [[ -d "$ROOT/{compile_main_path}" ]]; then',
            'if [[ -d "$ROOT/{{ compile_main_path }}" ]]; then',
        ),
        (
            f'"$python_bin" -m compileall "$ROOT/{compile_main_path}" >/dev/null',
            '"$python_bin" -m compileall "$ROOT/{{ compile_main_path }}" >/dev/null',
        ),
        (
            f'if [[ -d "$ROOT/{compile_test_path}" ]]; then',
            'if [[ -d "$ROOT/{{ compile_test_path }}" ]]; then',
        ),
        (
            f'"$python_bin" -m compileall "$ROOT/{compile_test_path}" >/dev/null',
            '"$python_bin" -m compileall "$ROOT/{{ compile_test_path }}" >/dev/null',
        ),
    ]

    for before, after in replacements:
        placeholderized = placeholderized.replace(before, after)

    json_field_patterns = {
        r'("workflow_repo_root"\s*:\s*)".*?"': r'\1"{{ workflow_repo_root }}"',
        r'("source_repo_root"\s*:\s*)".*?"': r'\1"{{ workflow_repo_root }}"',
        r'("repo_id"\s*:\s*)".*?"': r'\1"{{ repo_id }}"',
        r'("profile"\s*:\s*)".*?"': r'\1"{{ profile }}"',
        r'("expected_workspace_root"\s*:\s*)".*?"': r'\1"{{ expected_workspace_root }}"',
        r'("default_branch"\s*:\s*)".*?"': r'\1"{{ default_branch }}"',
        r'("python_package_name"\s*:\s*)".*?"': r'\1"{{ python_package_name }}"',
        r'("compile_main_path"\s*:\s*)".*?"': r'\1"{{ compile_main_path }}"',
        r'("compile_test_path"\s*:\s*)".*?"': r'\1"{{ compile_test_path }}"',
        r'("public_work_register_dir"\s*:\s*)".*?"': r'\1"{{ public_work_register_dir }}"',
        r'("workflow_version"\s*:\s*)".*?"': r'\1"{{ workflow_version }}"',
        r'("release_manifest_hash"\s*:\s*)".*?"': r'\1"{{ release_manifest_hash }}"',
    }
    for pattern, replacement in json_field_patterns.items():
        placeholderized = re.sub(pattern, replacement, placeholderized)
    return placeholderized


def export_runtime_templates(
    workflow_root: Path,
    repo_id: str,
    profile: str = DEFAULT_PROFILE,
) -> list[str]:
    repo_config = load_repo_config(workflow_root, repo_id)
    current_repo_id = repo_id_from_source_metadata(workflow_root.resolve())
    if current_repo_id == repo_id:
        repo_root = workflow_root.resolve()
    else:
        repo_root = Path(str(repo_config["expected_workspace_root"])).resolve()
    exported_paths: list[str] = []
    for entry in managed_runtime_entries(workflow_root, profile):
        source_path = repo_root / entry.output
        if not source_path.is_file():
            raise FileNotFoundError(f"runtime source entry not found: {source_path}")
        template_path = workflow_root / entry.template
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(
            placeholderize_runtime_entry(
                source_text=source_path.read_text(encoding="utf-8"),
                repo_config=repo_config,
                entry=entry,
            ),
            encoding="utf-8",
        )
        exported_paths.append(str(template_path))
    return exported_paths


def current_release_hash(current_release: dict[str, Any]) -> str:
    return str(current_release.get("release_manifest_hash") or release_manifest_hash(current_release))


def apply_release_to_repo(
    workflow_root: Path,
    repo_root: Path,
    repo_id: str | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_repo_id = resolve_repo_id(resolved_repo_root, repo_id)
    repo_config = load_repo_config(workflow_root, resolved_repo_id)
    resolved_profile = repo_profile(repo_config, profile)
    current_release = load_current_release(workflow_root, resolved_profile)
    workflow_version = str(current_release["workflow_version"])
    manifest_hash = current_release_hash(current_release)
    rendered_entries = render_repo_entries(
        workflow_root=workflow_root,
        repo_root=resolved_repo_root,
        repo_config=repo_config,
        workflow_version=workflow_version,
        release_hash=manifest_hash,
    )
    apply_rendered_entries(resolved_repo_root, rendered_entries)
    removed_legacy_paths: list[str] = []
    refreshed_wrapper_paths: list[str] = []
    refreshed_doc_paths: list[str] = []
    if resolved_repo_root != workflow_root.resolve():
        removed_legacy_paths = remove_legacy_managed_runtime_files(resolved_repo_root)
        refreshed_wrapper_paths = refresh_script_wrappers(resolved_repo_root)
        refreshed_doc_paths = refresh_workflow_doc_entrypoints(resolved_repo_root)
        ensure_local_exclude_patterns(resolved_repo_root)
        ensure_core_hooks_path(resolved_repo_root)
    return {
        "repo_root": str(resolved_repo_root),
        "repo_id": resolved_repo_id,
        "profile": resolved_profile,
        "workflow_version": workflow_version,
        "managed_entry_count": len(rendered_entries),
        "removed_legacy_paths": removed_legacy_paths,
        "refreshed_wrapper_paths": refreshed_wrapper_paths,
        "refreshed_doc_paths": refreshed_doc_paths,
    }


def write_release_artifacts(
    workflow_root: Path,
    profile: str,
    version: str,
    release_payload: dict[str, Any],
    lock_payload: dict[str, Any],
) -> None:
    release_current = release_json_path(workflow_root, profile)
    lock_current = lock_json_path(workflow_root, profile)
    history_dir = release_history_dir(workflow_root, profile, version)
    history_dir.mkdir(parents=True, exist_ok=True)
    write_json(release_current, release_payload)
    write_json(lock_current, lock_payload)
    write_json(history_dir / "release.json", release_payload)
    write_json(history_dir / "managed-files.lock.json", lock_payload)


def load_current_release(workflow_root: Path, profile: str) -> dict[str, Any]:
    path = release_json_path(workflow_root, profile)
    return load_required_json(path, "current release missing")


def load_current_lock(workflow_root: Path, profile: str) -> dict[str, Any]:
    path = lock_json_path(workflow_root, profile)
    return load_required_json(path, "current lock missing")


def load_versioned_lock(workflow_root: Path, profile: str, version: str) -> dict[str, Any]:
    version_path = release_history_dir(workflow_root, profile, version) / "managed-files.lock.json"
    if version_path.is_file():
        return load_json(version_path)
    current_path = lock_json_path(workflow_root, profile)
    if current_path.is_file():
        payload = load_json(current_path)
        if str(payload.get("workflow_version")) == version:
            return payload
    raise FileNotFoundError(f"managed lock missing for {profile}@{version}")


def repo_metadata_path(repo_root: Path, filename: str) -> Path:
    return repo_root / ".workflow-kit" / filename


def load_repo_source(repo_root: Path) -> dict[str, Any]:
    path = repo_metadata_path(repo_root, "source.json")
    return load_required_json(path, "workflow source metadata missing")


def load_repo_install(repo_root: Path) -> dict[str, Any]:
    path = repo_metadata_path(repo_root, "install.json")
    return load_required_json(path, "workflow install metadata missing")


def resolve_repo_id(repo_root: Path, repo_id: str | None = None) -> str:
    if repo_id is not None:
        return repo_id
    source_path = repo_metadata_path(repo_root, "source.json")
    if source_path.is_file():
        return str(load_repo_source(repo_root).get("repo_id") or repo_root.name)
    return repo_root.name


def check_repo_release(
    repo_root: Path,
    workflow_root: Path | None = None,
    repo_id: str | None = None,
) -> dict[str, Any]:
    source = load_repo_source(repo_root)
    resolved_repo_id = resolve_repo_id(repo_root, repo_id)
    install = load_repo_install(repo_root)
    profile = str(install.get("profile") or source.get("profile") or DEFAULT_PROFILE)
    workflow_source_root = workflow_root or Path(str(source.get("workflow_repo_root") or source.get("source_repo_root", "")))
    if not workflow_source_root.is_dir():
        raise FileNotFoundError(f"workflow source root not found: {workflow_source_root}")
    current_release = load_current_release(workflow_source_root, profile)
    installed_version = str(install.get("workflow_version", ""))
    current_version = str(current_release.get("workflow_version", ""))
    installed_lock = load_versioned_lock(workflow_source_root, profile, installed_version)
    repo_lock = installed_lock.get("repositories", {}).get(resolved_repo_id, {})
    lock_entries = list(repo_lock.get("entries", []))
    mismatches: list[dict[str, Any]] = []
    for entry in lock_entries:
        target = repo_root / str(entry["path"])
        if entry["type"] == "file":
            if not target.is_file():
                mismatches.append({"path": entry["path"], "reason": "missing-file"})
                continue
            actual_hash = sha256_bytes(target.read_bytes())
        else:
            if not target.is_file():
                mismatches.append({"path": entry["path"], "reason": "missing-block-file"})
                continue
            extracted = extract_block(
                text=target.read_text(encoding="utf-8"),
                start_marker=str(entry["start_marker"]),
                end_marker=str(entry["end_marker"]),
            )
            if extracted is None:
                mismatches.append({"path": entry["path"], "reason": "missing-block"})
                continue
            actual_hash = sha256_text(extracted)
        if actual_hash != entry["sha256"]:
            mismatches.append({"path": entry["path"], "reason": "hash-mismatch"})
    if mismatches:
        status = "drift"
        exit_code = DRIFT_RELEASE_EXIT
    elif installed_version != current_version:
        status = "outdated"
        exit_code = OUTDATED_RELEASE_EXIT
    else:
        status = "current"
        exit_code = CURRENT_RELEASE_EXIT
    return {
        "repo_root": str(repo_root),
        "repo_id": resolved_repo_id,
        "profile": profile,
        "workflow_source_root": str(workflow_source_root),
        "installed_version": installed_version,
        "current_version": current_version,
        "status": status,
        "exit_code": exit_code,
        "mismatches": mismatches,
    }


def _command_output_summary(process: subprocess.CompletedProcess[str]) -> str:
    parts = [process.stdout.strip(), process.stderr.strip()]
    return "\n".join(part for part in parts if part)


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if process.returncode == 0:
        return process
    output = _command_output_summary(process)
    suffix = f"\n{output}" if output else ""
    raise RuntimeError(f"command failed ({process.returncode}): {' '.join(args)}{suffix}")


def _git_output(repo_root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return _run_command(["git", "-C", str(repo_root), *args], env=env).stdout.strip()


def _git_status_paths(repo_root: Path) -> list[str]:
    status_output = _git_output(repo_root, "status", "--short")
    paths: list[str] = []
    for raw_line in status_output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _resolve_runtime_script(repo_root: Path, basename: str) -> Path | None:
    for runtime_dir in MANAGED_RUNTIME_DIRS:
        candidate = repo_root / runtime_dir / basename
        if candidate.is_file():
            return candidate
    return None


def _downstream_issue_slug(workflow_version: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z]+", "-", workflow_version).strip("-").lower()
    suffix = normalized or "current"
    return f"workflow-release-{suffix}"


def _parse_new_worktree_output(output: str) -> tuple[str, Path, str]:
    branch_match = re.search(r"(?m)^  branch:\s+(.+)$", output)
    path_match = re.search(r"(?m)^  path:\s+(.+)$", output)
    exec_match = re.search(r"(?m)^  exec:\s+([0-9]{4,})$", output)
    if branch_match is None or path_match is None or exec_match is None:
        raise RuntimeError(f"unable to parse downstream worktree creation output:\n{output.strip()}")
    return branch_match.group(1).strip(), Path(path_match.group(1).strip()), exec_match.group(1).strip()


def _cleanup_worktree(primary_repo_root: Path, worktree_root: Path, branch: str) -> None:
    errors: list[str] = []
    if worktree_root.exists():
        try:
            _run_command(["git", "-C", str(primary_repo_root), "worktree", "remove", "--force", str(worktree_root)])
        except Exception as exc:  # pragma: no cover - best effort cleanup
            errors.append(str(exc))
    try:
        _run_command(["git", "-C", str(primary_repo_root), "branch", "-D", branch])
    except Exception as exc:  # pragma: no cover - best effort cleanup
        errors.append(str(exc))
    if errors:
        raise RuntimeError("\n".join(errors))


def _render_changed_paths(paths: list[str], limit: int = 20) -> str:
    visible = paths[:limit]
    lines = [f"- {path}" for path in visible]
    if len(paths) > limit:
        lines.append(f"- ... ({len(paths) - limit} more)")
    return "\n".join(lines) if lines else "- none"


def _write_downstream_exec_record(
    worktree_root: Path,
    *,
    exec_id: str,
    repo_id: str,
    profile: str,
    workflow_version: str,
    default_branch: str,
    changed_paths: list[str],
    commit_message: str,
) -> None:
    today = date.today().isoformat()
    changed_path_block = _render_changed_paths(changed_paths)
    record_path = worktree_root / "docs" / "exec_records" / f"{exec_id}.md"
    commit_template_path = worktree_root / "docs" / "exec_records" / f"{exec_id}_commit.txt"
    record_path.write_text(
        (
            f"# {exec_id}\n\n"
            "## 完成定义（DoD）\n\n"
            "- [x] 需求目标已明确（本次只做本地提交，不自动 push/release）\n"
            "- [ ] 变更验证命令已执行并记录\n"
            f"- [ ] 若为代码任务：已合并到目标分支并完成分支清理（目标分支：{default_branch}）\n\n"
            "## 需求摘要\n\n"
            f"将中央仓库当前发布的 `{profile}@{workflow_version}` 应用到 `{repo_id}`，并在子仓库 worktree 中生成本地提交。\n\n"
            "## 变更文件\n\n"
            f"{changed_path_block}\n\n"
            "## 变更说明\n\n"
            f"- 通过受管 worktree 提交流程下推 `{profile}@{workflow_version}`。\n"
            "- 保留 worktree 供后续人工检查、push 或 release。\n\n"
            "## 验证结果\n\n"
            "- 未自动执行测试；仅验证受管文件已生成本地提交。\n\n"
            "## 完成待办项\n\n"
            "- 无\n\n"
            "## 当前占用待办项\n\n"
            "- 本地 worktree 待后续 push/release。\n\n"
            "## 风险与回滚\n\n"
            "- 风险：当前变更仅存在于本地 worktree，尚未推送。\n"
            "- 回滚：删除该 worktree 与本地分支，或在子仓库中回退此 commit。\n"
            f"\n## 记录时间\n\n- {today}\n"
        ),
        encoding="utf-8",
    )
    commit_template_path.write_text(
        (
            f"{commit_message}\n\n"
            "# Changes\n"
            f"# - apply {profile}@{workflow_version} into downstream repo {repo_id}\n"
            "# - keep the resulting worktree local for later push/release\n\n"
            "# Tests\n"
            "# - not run (local downstream commit only)\n\n"
            "# Risks\n"
            "# - downstream worktree remains local and still needs manual push/release\n"
        ),
        encoding="utf-8",
    )


def submit_release_to_repo_via_worktree_commit(
    workflow_root: Path,
    repo_root: Path,
    repo_id: str | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    resolved_repo_root = repo_root.expanduser().resolve()
    summary: dict[str, Any] = {
        "repo_root": str(resolved_repo_root),
        "repo_id": repo_id or resolved_repo_root.name,
        "profile": profile,
        "workflow_version": "",
        "installed_version": "",
        "current_version": "",
        "status_before": "unknown",
        "action": "failed",
        "worktree_path": None,
        "branch": None,
        "exec_id": None,
        "commit_sha": None,
        "commit_message": None,
        "changed_paths": [],
        "error": None,
    }

    try:
        release_status = check_repo_release(
            repo_root=resolved_repo_root,
            workflow_root=workflow_root,
            repo_id=repo_id,
        )
        resolved_repo_id = str(release_status["repo_id"])
        resolved_profile = str(release_status["profile"])
        current_release = load_current_release(workflow_root, resolved_profile)
        workflow_version = str(current_release["workflow_version"])
        summary.update(
            {
                "repo_id": resolved_repo_id,
                "profile": resolved_profile,
                "workflow_version": workflow_version,
                "installed_version": str(release_status["installed_version"]),
                "current_version": str(release_status["current_version"]),
                "status_before": str(release_status["status"]),
            }
        )

        if release_status["status"] == "current":
            summary["action"] = "skip-current"
            return summary

        repo_config = load_repo_config(workflow_root, resolved_repo_id)
        default_branch = str(repo_config["default_branch"])
        worktree_env = {
            **os.environ,
            "WORKFLOW_GUARD_ACTIVE": "1",
            # Older downstream runtimes link .venv before session_sync and can dirty
            # the freshly created worktree. Skip that bootstrap step until the
            # current release is applied and can repair excludes first.
            "SKIP_SHARED_VENV_LINK": "1",
        }
        script_path = _resolve_runtime_script(resolved_repo_root, "new_worktree.sh")
        if script_path is None:
            raise FileNotFoundError(
                "downstream worktree script not found under .workflow-kit/ or .git_scripts/"
            )

        issue_slug = _downstream_issue_slug(workflow_version)
        worktree_process = _run_command(
            [str(script_path), issue_slug],
            cwd=resolved_repo_root,
            env=worktree_env,
        )
        branch, worktree_root, exec_id = _parse_new_worktree_output(
            _command_output_summary(worktree_process) or worktree_process.stdout
        )
        summary.update(
            {
                "worktree_path": str(worktree_root),
                "branch": branch,
                "exec_id": exec_id,
            }
        )

        baseline_paths = set(_git_status_paths(worktree_root))
        apply_release_to_repo(
            workflow_root=workflow_root,
            repo_root=worktree_root,
            repo_id=resolved_repo_id,
            profile=resolved_profile,
        )
        repair_shared_venv_script = worktree_root / MANAGED_WORKFLOW_DIR / "ensure_shared_venv.sh"
        if repair_shared_venv_script.is_file():
            _run_command(
                [str(repair_shared_venv_script), "--quiet"],
                cwd=worktree_root,
                env={**os.environ, "WORKFLOW_GUARD_ACTIVE": "1"},
            )
        after_paths = set(_git_status_paths(worktree_root))
        managed_release_paths = sorted(after_paths - baseline_paths)
        if not managed_release_paths:
            _cleanup_worktree(resolved_repo_root, worktree_root, branch)
            summary["action"] = "noop-cleanup"
            return summary

        changed_paths = sorted(after_paths)
        commit_message = f"[{exec_id}] chore(workflow): apply {resolved_profile}@{workflow_version}"
        _write_downstream_exec_record(
            worktree_root,
            exec_id=exec_id,
            repo_id=resolved_repo_id,
            profile=resolved_profile,
            workflow_version=workflow_version,
            default_branch=default_branch,
            changed_paths=changed_paths,
            commit_message=commit_message,
        )
        commit_env = {
            **os.environ,
            "WORKFLOW_GUARD_ACTIVE": "1",
            "SKIP_APPLY_DOWNSTREAMS_AFTER_COMMIT": "1",
            "SKIP_AUTO_PUSH_AFTER_COMMIT": "1",
        }
        _run_command(["git", "-C", str(worktree_root), "add", "-A"], env=commit_env)
        _run_command(["git", "-C", str(worktree_root), "commit", "-m", commit_message], env=commit_env)
        commit_sha = _git_output(worktree_root, "rev-parse", "HEAD")
        summary.update(
            {
                "action": "committed",
                "commit_sha": commit_sha,
                "commit_message": commit_message,
                "changed_paths": changed_paths,
            }
        )
        return summary
    except Exception as exc:
        summary["error"] = str(exc)
        return summary
