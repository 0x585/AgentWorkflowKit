from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = "full_codex_flow"
MANAGED_GIT_SCRIPTS_DIR = ".git_scripts"
MANAGED_HOOKS_DIR = ".githooks"
MANAGED_RUNTIME_BASENAMES = (
    "workflow_guard.sh",
    "assert_workspace.sh",
    "setup_githooks.sh",
    "git_default_branch.sh",
    "new_branch.sh",
    "new_worktree.sh",
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
WORKFLOW_EXCLUDE_MARKER_START = "# workflow-kit managed excludes start"
WORKFLOW_EXCLUDE_MARKER_END = "# workflow-kit managed excludes end"
DOWNSTREAM_EXCLUDE_PATTERNS = (
    f"{MANAGED_GIT_SCRIPTS_DIR}/",
    f"{MANAGED_HOOKS_DIR}/",
)
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
        "python_package_name": str(repo_config["python_package_name"]),
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
    payload = {
        "type": entry.entry_type,
        "path": entry.output,
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
    managed_block = (
        f"{WORKFLOW_EXCLUDE_MARKER_START}\n"
        + "\n".join(patterns)
        + f"\n{WORKFLOW_EXCLUDE_MARKER_END}\n"
    )
    if WORKFLOW_EXCLUDE_MARKER_START in existing and WORKFLOW_EXCLUDE_MARKER_END in existing:
        prefix, remainder = existing.split(WORKFLOW_EXCLUDE_MARKER_START, 1)
        _, suffix = remainder.split(WORKFLOW_EXCLUDE_MARKER_END, 1)
        updated = prefix.rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += managed_block.rstrip("\n")
        suffix = suffix.lstrip("\n")
        if suffix:
            updated += "\n\n" + suffix
        updated += "\n"
    else:
        updated = existing.rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += managed_block
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
    removed_paths: list[str] = []
    for basename in MANAGED_RUNTIME_BASENAMES:
        legacy_path = repo_root / "scripts" / basename
        if legacy_path.is_file():
            legacy_path.unlink()
            removed_paths.append(str(legacy_path))
    return removed_paths


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
        and (entry.output.startswith(f"{MANAGED_GIT_SCRIPTS_DIR}/") or entry.output.startswith(f"{MANAGED_HOOKS_DIR}/"))
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
            f'EXPECTED_ROOT="${{EXPECTED_WORKSPACE_ROOT:-{expected_root}}}"',
            'EXPECTED_ROOT="${EXPECTED_WORKSPACE_ROOT:-{{ expected_workspace_root }}}"',
        ),
        (
            f'DEFAULT_BRANCH="$("$ROOT/{MANAGED_GIT_SCRIPTS_DIR}/git_default_branch.sh" "$EXPECTED_ROOT" 2>/dev/null || echo {default_branch})"',
            'DEFAULT_BRANCH="$("$ROOT/.git_scripts/git_default_branch.sh" "$EXPECTED_ROOT" 2>/dev/null || echo {{ default_branch }})"',
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
    if resolved_repo_root != workflow_root.resolve():
        removed_legacy_paths = remove_legacy_managed_runtime_files(resolved_repo_root)
        ensure_local_exclude_patterns(resolved_repo_root)
        ensure_core_hooks_path(resolved_repo_root)
    return {
        "repo_root": str(resolved_repo_root),
        "repo_id": resolved_repo_id,
        "profile": resolved_profile,
        "workflow_version": workflow_version,
        "managed_entry_count": len(rendered_entries),
        "removed_legacy_paths": removed_legacy_paths,
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
