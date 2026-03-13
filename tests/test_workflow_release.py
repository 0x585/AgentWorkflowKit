from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.workflow_kit_lib import (
    apply_release_to_repo,
    apply_rendered_entries,
    build_lock_manifest,
    check_repo_release,
    export_runtime_templates,
    inject_block,
    load_json,
    load_repo_config,
    prepare_release_artifacts,
    render_repo_entries,
    submit_release_to_repo_via_worktree_commit,
    write_release_artifacts,
    write_json,
)


class WorkflowReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_root = Path(__file__).resolve().parents[1]
        self.version = "1.0.0"
        self.release_payload, _ = prepare_release_artifacts(
            workflow_root=self.workflow_root,
            profile="full_codex_flow",
            version=self.version,
            repo_ids=["AgentTask", "AgentTransitStation"],
        )
        self.release_hash = str(self.release_payload["release_manifest_hash"])

    def snapshot_files(self, repo_root: Path) -> dict[str, str]:
        return {
            str(path.relative_to(repo_root)): path.read_text(encoding="utf-8")
            for path in sorted(repo_root.rglob("*"))
            if path.is_file()
        }

    def write_repo_docs(self, repo_root: Path) -> None:
        (repo_root / "README.md").write_text("# Temp Repo\n", encoding="utf-8")
        (repo_root / "AGENTS.md").write_text("# Temp Agents\n", encoding="utf-8")
        exec_dir = repo_root / "docs" / "exec_records"
        exec_dir.mkdir(parents=True, exist_ok=True)
        (exec_dir / "INDEX.md").write_text(
            "# Execution Records\n\n| ID | Date | Summary |\n|---|---|---|\n",
            encoding="utf-8",
        )

    def copy_runtime_sources(self, target_root: Path) -> None:
        shutil.copytree(self.workflow_root / ".git_scripts", target_root / ".git_scripts")
        shutil.copytree(self.workflow_root / ".githooks", target_root / ".githooks")

    def copy_workflow_repo(self, workflow_root: Path) -> None:
        shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
        shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
        shutil.copytree(self.workflow_root / "repos", workflow_root / "repos")
        shutil.copytree(self.workflow_root / "scripts", workflow_root / "scripts")

    def write_temp_repo_config(self, workflow_root: Path, repo_root: Path) -> dict[str, str]:
        resolved_repo_root = repo_root.resolve()
        repo_config = {
            "repo_id": "TempRepo",
            "profile": "full_codex_flow",
            "expected_workspace_root": str(resolved_repo_root),
            "default_branch": "main",
            "python_package_name": "temp_repo",
            "compile_main_path": "src/main/python/temp_repo",
            "compile_test_path": "src/test/python/temp_repo",
            "public_work_register_dir": str((resolved_repo_root.parent / "PublicWorkRegister" / "TempRepo").resolve()),
        }
        write_json(workflow_root / "repos" / "TempRepo.json", repo_config)
        return repo_config

    def write_named_repo_config(
        self,
        workflow_root: Path,
        repo_root: Path,
        *,
        repo_id: str,
        default_branch: str = "main",
    ) -> dict[str, str]:
        resolved_repo_root = repo_root.resolve()
        python_package_name = repo_id.lower()
        repo_config = {
            "repo_id": repo_id,
            "profile": "full_codex_flow",
            "expected_workspace_root": str(resolved_repo_root),
            "default_branch": default_branch,
            "python_package_name": python_package_name,
            "compile_main_path": f"src/main/python/{python_package_name}",
            "compile_test_path": f"src/test/python/{python_package_name}",
            "public_work_register_dir": str((resolved_repo_root.parent / "PublicWorkRegister" / repo_id).resolve()),
        }
        write_json(workflow_root / "repos" / f"{repo_id}.json", repo_config)
        return repo_config

    def git(self, repo_root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def init_git_repo(self, repo_root: Path, default_branch: str = "main") -> None:
        subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
        self.git(repo_root, "config", "user.name", "Workflow Test")
        self.git(repo_root, "config", "user.email", "workflow@example.com")
        self.git(repo_root, "checkout", "-b", default_branch)

    def bootstrap_managed_repo(
        self,
        workflow_root: Path,
        repo_root: Path,
        *,
        repo_id: str = "TempRepo",
        default_branch: str = "main",
        installed_version: str = "1.0.0",
    ) -> dict[str, str]:
        repo_root.mkdir(parents=True)
        self.init_git_repo(repo_root, default_branch=default_branch)
        self.write_repo_docs(repo_root)
        repo_config = self.write_named_repo_config(
            workflow_root,
            repo_root,
            repo_id=repo_id,
            default_branch=default_branch,
        )
        self.publish_release_for_repo_ids(workflow_root, installed_version, [repo_id])
        apply_release_to_repo(workflow_root=workflow_root, repo_root=repo_root, repo_id=repo_id)
        self.git(repo_root, "add", "-A")
        self.git(repo_root, "add", "-f", ".git_scripts", ".githooks")
        self.git(repo_root, "commit", "--no-verify", "-m", "init")
        remote_root = repo_root.parent / f"{repo_id}-remote.git"
        subprocess.run(["git", "init", "--bare", str(remote_root)], check=True, capture_output=True, text=True)
        self.git(repo_root, "remote", "add", "origin", str(remote_root))
        self.git(repo_root, "push", "--no-verify", "-u", "origin", default_branch)
        return repo_config

    def publish_release_for_repo_ids(
        self,
        workflow_root: Path,
        version: str,
        repo_ids: list[str],
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, lock_payload = prepare_release_artifacts(
            workflow_root=workflow_root,
            profile="full_codex_flow",
            version=version,
            repo_ids=repo_ids,
        )
        write_release_artifacts(
            workflow_root=workflow_root,
            profile="full_codex_flow",
            version=version,
            release_payload=payload,
            lock_payload=lock_payload,
        )
        return payload, lock_payload

    def publish_temp_release(self, workflow_root: Path, version: str) -> str:
        payload, _ = self.publish_release_for_repo_ids(workflow_root, version, ["TempRepo"])
        return str(payload["release_manifest_hash"])

    def test_repo_specific_render_differs(self) -> None:
        agent_task = load_repo_config(self.workflow_root, "AgentTask")
        agent_transit = load_repo_config(self.workflow_root, "AgentTransitStation")
        task_entries = render_repo_entries(
            workflow_root=self.workflow_root,
            repo_root=Path(agent_task["expected_workspace_root"]),
            repo_config=agent_task,
            workflow_version=self.version,
            release_hash=self.release_hash,
        )
        transit_entries = render_repo_entries(
            workflow_root=self.workflow_root,
            repo_root=Path(agent_transit["expected_workspace_root"]),
            repo_config=agent_transit,
            workflow_version=self.version,
            release_hash=self.release_hash,
        )
        task_assert = next(entry for entry in task_entries if entry["path"] == ".git_scripts/assert_workspace.sh")
        transit_assert = next(entry for entry in transit_entries if entry["path"] == ".git_scripts/assert_workspace.sh")
        task_agents = next(entry for entry in task_entries if entry["path"] == "AGENTS.md")
        task_readme = next(entry for entry in task_entries if entry["path"] == "README.md")
        task_service = next(
            entry
            for entry in task_entries
            if entry["path"] == "src/main/python/agent_task/tooling/service/public_work_register_service.py"
        )
        transit_service = next(
            entry
            for entry in transit_entries
            if entry["path"] == "src/main/python/agent_transit_station/tooling/service/public_work_register_service.py"
        )
        self.assertIn("/Users/pi/PyCharmProject/AgentTask", task_assert["content"])
        self.assertIn("/Users/pi/PyCharmProject/AgentTransitStation", transit_assert["content"])
        self.assertNotEqual(task_assert["sha256"], transit_assert["sha256"])
        self.assertNotIn("AgentWorkflowKit", task_agents["content"])
        self.assertNotIn("/Users/pi/PyCharmProject/AgentWorkflowKit", task_agents["content"])
        self.assertNotIn("AgentWorkflowKit", task_readme["content"])
        self.assertNotIn("/Users/pi/PyCharmProject/AgentWorkflowKit", task_readme["content"])
        self.assertIn("AGENT_TASK_PUBLIC_WORK_REGISTER_ROOT", task_service["content"])
        self.assertIn("AGENT_TRANSIT_STATION_PUBLIC_WORK_REGISTER_ROOT", transit_service["content"])
        self.assertNotEqual(task_service["path"], transit_service["path"])

    def test_apply_rendered_entries_is_idempotent(self) -> None:
        repo_config = load_repo_config(self.workflow_root, "AgentTask").copy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            repo_config["repo_id"] = "AgentTask"
            repo_config["expected_workspace_root"] = str(repo_root)
            self.write_repo_docs(repo_root)
            rendered_entries = render_repo_entries(
                workflow_root=self.workflow_root,
                repo_root=repo_root,
                repo_config=repo_config,
                workflow_version=self.version,
                release_hash=self.release_hash,
            )
            apply_rendered_entries(repo_root, rendered_entries)
            first_snapshot = self.snapshot_files(repo_root)
            apply_rendered_entries(repo_root, rendered_entries)
            second_snapshot = self.snapshot_files(repo_root)
            self.assertEqual(first_snapshot, second_snapshot)

    def test_lock_manifest_contains_repo_entries(self) -> None:
        lock_payload = build_lock_manifest(
            workflow_root=self.workflow_root,
            profile="full_codex_flow",
            version=self.version,
            release_hash=self.release_hash,
        )
        self.assertIn("AgentTask", lock_payload["repositories"])
        self.assertIn("AgentTransitStation", lock_payload["repositories"])
        task_paths = {entry["path"] for entry in lock_payload["repositories"]["AgentTask"]["entries"]}
        transit_paths = {entry["path"] for entry in lock_payload["repositories"]["AgentTransitStation"]["entries"]}
        self.assertIn(".git_scripts/new_exec.sh", task_paths)
        self.assertIn(".git_scripts/new_exec.sh", transit_paths)
        self.assertIn(".git_scripts/ensure_shared_venv.sh", task_paths)
        self.assertIn(".git_scripts/ensure_shared_venv.sh", transit_paths)
        self.assertIn("src/main/python/agent_task/tooling/service/public_work_register_service.py", task_paths)
        self.assertIn("src/main/python/agent_transit_station/tooling/service/public_work_register_service.py", transit_paths)

    def test_inject_block_replaces_managed_region(self) -> None:
        original = "# Header\n\n<!-- workflow-kit:readme:start -->\nold\n<!-- workflow-kit:readme:end -->\n"
        updated = inject_block(
            original=original,
            start_marker="<!-- workflow-kit:readme:start -->",
            end_marker="<!-- workflow-kit:readme:end -->",
            managed_text="new content\n",
        )
        self.assertIn("new content", updated)
        self.assertNotIn("\nold\n", updated)

    def test_apply_release_to_repo_ignores_managed_git_runtime_and_removes_legacy_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            shutil.copytree(self.workflow_root / "repos", workflow_root / "repos")

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            self.write_repo_docs(repo_root)
            legacy_scripts_dir = repo_root / "scripts"
            legacy_scripts_dir.mkdir(parents=True, exist_ok=True)
            legacy_file = legacy_scripts_dir / "new_branch.sh"
            legacy_file.write_text("# legacy\n", encoding="utf-8")

            repo_config = {
                "repo_id": "TempRepo",
                "profile": "full_codex_flow",
                "expected_workspace_root": str(repo_root),
                "default_branch": "main",
                "python_package_name": "temp_repo",
                "compile_main_path": "src/main/python/temp_repo",
                "compile_test_path": "src/test/python/temp_repo",
                "public_work_register_dir": str(temp_root / "PublicWorkRegister" / "TempRepo"),
            }
            write_json(workflow_root / "repos" / "TempRepo.json", repo_config)
            payload, lock_payload = prepare_release_artifacts(
                workflow_root=workflow_root,
                profile="full_codex_flow",
                version="1.0.0",
                repo_ids=["TempRepo"],
            )
            write_release_artifacts(
                workflow_root=workflow_root,
                profile="full_codex_flow",
                version="1.0.0",
                release_payload=payload,
                lock_payload=lock_payload,
            )

            summary = apply_release_to_repo(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("TempRepo", summary["repo_id"])
            self.assertIn(str(legacy_file.resolve()), summary["removed_legacy_paths"])
            self.assertFalse(legacy_file.exists())
            self.assertTrue((repo_root / ".git_scripts" / "new_branch.sh").is_file())
            self.assertTrue((repo_root / ".git_scripts" / "ensure_shared_venv.sh").is_file())
            self.assertTrue(
                (
                    repo_root
                    / "src"
                    / "main"
                    / "python"
                    / "temp_repo"
                    / "tooling"
                    / "service"
                    / "public_work_register_service.py"
                ).is_file()
            )

            exclude_path = Path(
                subprocess.run(
                    ["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            exclude_path.write_text(
                "\n".join(
                    [
                        "# keep-me",
                        "# workflow-kit managed excludes start",
                        ".githooks/",
                        ".git_scripts/",
                        "# workflow-kit managed excludes end",
                        "# keep-me-too",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            summary = apply_release_to_repo(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            exclude_text = exclude_path.read_text(encoding="utf-8")
            self.assertNotIn(".githooks/", exclude_text)
            self.assertNotIn(".git_scripts/", exclude_text)
            self.assertNotIn("# workflow-kit managed excludes start", exclude_text)
            self.assertIn("# keep-me", exclude_text)
            self.assertIn("# keep-me-too", exclude_text)
            hooks_path = subprocess.run(
                ["git", "-C", str(repo_root), "config", "--local", "--get", "core.hooksPath"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(".githooks", hooks_path)

    def test_export_runtime_templates_restores_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            shutil.copytree(self.workflow_root / "repos", workflow_root / "repos")
            self.copy_runtime_sources(workflow_root)
            write_json(workflow_root / ".workflow-kit" / "source.json", {"repo_id": "AgentWorkflowKit"})

            exported = export_runtime_templates(workflow_root=workflow_root, repo_id="AgentWorkflowKit")
            self.assertTrue(exported)

            assert_workspace_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".git_scripts" / "assert_workspace.sh.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ expected_workspace_root }}", assert_workspace_template)
            self.assertIn("{{ default_branch }}", assert_workspace_template)
            self.assertNotIn("/Users/pi/PyCharmProject/AgentWorkflowKit", assert_workspace_template)

            default_branch_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".git_scripts" / "git_default_branch.sh.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn('PREFERRED_BRANCH="{{ default_branch }}"', default_branch_template)

            pre_push_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".githooks" / "pre-push.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ compile_main_path }}", pre_push_template)
            self.assertIn("{{ compile_test_path }}", pre_push_template)
            self.assertNotIn("src/main/python/agent_workflow_kit", pre_push_template)

            register_sync_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".git_scripts" / "public_work_register_sync.py.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ python_package_name }}", register_sync_template)
            self.assertNotIn("agent_workflow_kit.tooling.service", register_sync_template)

    def test_ensure_shared_venv_links_primary_virtualenv_into_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(repo_root), "config", "user.name", "Workflow Test"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "config", "user.email", "workflow@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )
            (repo_root / "README.md").write_text("# Temp Repo\n", encoding="utf-8")
            (repo_root / ".git_scripts").mkdir(parents=True, exist_ok=True)
            helper_path = repo_root / ".git_scripts" / "ensure_shared_venv.sh"
            helper_path.write_text(
                (self.workflow_root / ".git_scripts" / "ensure_shared_venv.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            helper_path.chmod(0o755)
            subprocess.run(
                ["git", "-C", str(repo_root), "add", "README.md", ".git_scripts/ensure_shared_venv.sh"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "commit", "--no-verify", "-m", "init"],
                check=True,
                capture_output=True,
                text=True,
            )

            primary_python = repo_root / ".venv" / "bin" / "python"
            primary_python.parent.mkdir(parents=True, exist_ok=True)
            primary_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            primary_python.chmod(0o755)

            worktree_root = temp_root / "TempRepo-wt-link"
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "-b", "codex/link-test", str(worktree_root), "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )

            subprocess.run(
                [str(helper_path), "--target-root", str(worktree_root)],
                check=True,
                capture_output=True,
                text=True,
                env={"WORKFLOW_GUARD_ACTIVE": "1", **os.environ},
            )

            worktree_venv = worktree_root / ".venv"
            self.assertTrue(worktree_venv.is_symlink())
            linked_target = Path(os.readlink(worktree_venv)).resolve()
            self.assertEqual((repo_root / ".venv").resolve(), linked_target)

    def test_check_release_detects_outdated_then_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            (workflow_root / "repos").mkdir(parents=True)

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            self.write_repo_docs(repo_root)

            repo_config = {
                "repo_id": "TempRepo",
                "profile": "full_codex_flow",
                "expected_workspace_root": str(repo_root),
                "default_branch": "main",
                "python_package_name": "temp_repo",
                "compile_main_path": "src/main/python/temp_repo",
                "compile_test_path": "src/test/python/temp_repo",
                "public_work_register_dir": str(temp_root / "PublicWorkRegister" / "TempRepo"),
            }
            write_json(workflow_root / "repos" / "TempRepo.json", repo_config)

            def publish(version: str) -> str:
                payload, lock_payload = prepare_release_artifacts(
                    workflow_root=workflow_root,
                    profile="full_codex_flow",
                    version=version,
                    repo_ids=["TempRepo"],
                )
                write_release_artifacts(
                    workflow_root=workflow_root,
                    profile="full_codex_flow",
                    version=version,
                    release_payload=payload,
                    lock_payload=lock_payload,
                )
                return str(payload["release_manifest_hash"])

            manifest_hash_v1 = publish("1.0.0")
            rendered_v1 = render_repo_entries(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_config=repo_config,
                workflow_version="1.0.0",
                release_hash=manifest_hash_v1,
            )
            apply_rendered_entries(repo_root, rendered_v1)

            current = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("current", current["status"])

            publish("1.0.1")
            outdated = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("outdated", outdated["status"])

            target_script = repo_root / ".git_scripts" / "new_branch.sh"
            target_script.write_text(target_script.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
            drift = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("drift", drift["status"])

    def test_git_default_branch_prefers_repo_default_branch_over_stale_origin_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)
            self.copy_runtime_sources(workflow_root)
            write_json(workflow_root / ".workflow-kit" / "source.json", {"repo_id": "AgentWorkflowKit"})
            export_runtime_templates(workflow_root=workflow_root, repo_id="AgentWorkflowKit")

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(repo_root), "config", "user.name", "Workflow Test"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "config", "user.email", "workflow@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.write_repo_docs(repo_root)
            self.write_temp_repo_config(workflow_root, repo_root)
            self.publish_temp_release(workflow_root, "1.0.0")
            apply_release_to_repo(workflow_root=workflow_root, repo_root=repo_root, repo_id="TempRepo")

            readme_path = repo_root / "README.md"
            subprocess.run(["git", "-C", str(repo_root), "add", str(readme_path)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(repo_root), "commit", "--no-verify", "-m", "init"],
                check=True,
                capture_output=True,
                text=True,
            )
            head_sha = subprocess.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(repo_root), "update-ref", "refs/remotes/origin/master", head_sha],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "update-ref", "refs/remotes/origin/main", head_sha],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master"],
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [str(repo_root / ".git_scripts" / "git_default_branch.sh"), str(repo_root)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual("main", result.stdout.strip())

    def test_workflow_guard_skips_release_check_when_entry_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            self.write_repo_docs(repo_root)
            self.write_temp_repo_config(workflow_root, repo_root)

            self.publish_temp_release(workflow_root, "1.0.0")
            apply_release_to_repo(workflow_root=workflow_root, repo_root=repo_root, repo_id="TempRepo")
            self.publish_temp_release(workflow_root, "1.0.1")

            entry_script = repo_root / "entry.sh"
            entry_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            entry_script.chmod(0o755)

            result = subprocess.run(
                [str(repo_root / ".git_scripts" / "workflow_guard.sh"), str(entry_script)],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode)
            self.assertNotIn("Applying latest release", result.stderr)
            install = load_json(repo_root / ".workflow-kit" / "install.json")
            self.assertEqual("1.0.0", install["workflow_version"])

    def test_workflow_guard_upgrades_after_entry_failure_then_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            self.write_repo_docs(repo_root)
            self.write_temp_repo_config(workflow_root, repo_root)

            self.publish_temp_release(workflow_root, "1.0.0")
            apply_release_to_repo(workflow_root=workflow_root, repo_root=repo_root, repo_id="TempRepo")
            self.publish_temp_release(workflow_root, "1.0.1")

            entry_script = repo_root / "entry.sh"
            entry_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail

version="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('.workflow-kit/install.json').read_text(encoding='utf-8'))['workflow_version'])
PY
)"
printf '%s\n' "$version" >> entry.log
if [[ "$version" == "1.0.1" ]]; then
  exit 0
fi
exit 42
""",
                encoding="utf-8",
            )
            entry_script.chmod(0o755)

            result = subprocess.run(
                [str(repo_root / ".git_scripts" / "workflow_guard.sh"), str(entry_script)],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode)
            self.assertIn("Applying latest release and retrying", result.stderr)
            install = load_json(repo_root / ".workflow-kit" / "install.json")
            self.assertEqual("1.0.1", install["workflow_version"])
            entry_runs = (repo_root / "entry.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(["1.0.0", "1.0.1"], entry_runs)

    def test_submit_release_to_repo_via_worktree_commit_skips_current_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            self.bootstrap_managed_repo(workflow_root, repo_root, repo_id="TempRepo", installed_version="1.0.0")

            summary = submit_release_to_repo_via_worktree_commit(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("skip-current", summary["action"])
            self.assertEqual("current", summary["status_before"])
            self.assertIsNone(summary["worktree_path"])
            self.assertIsNone(summary["commit_sha"])
            worktree_count = len(
                [
                    line
                    for line in self.git(repo_root, "worktree", "list", "--porcelain").stdout.splitlines()
                    if line.startswith("worktree ")
                ]
            )
            self.assertEqual(1, worktree_count)

    def test_submit_release_to_repo_via_worktree_commit_creates_local_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            self.bootstrap_managed_repo(workflow_root, repo_root, repo_id="TempRepo", installed_version="1.0.0")
            self.publish_temp_release(workflow_root, "1.0.1")

            summary = submit_release_to_repo_via_worktree_commit(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("committed", summary["action"])
            self.assertEqual("outdated", summary["status_before"])
            self.assertTrue(str(summary["branch"]).startswith("codex/workflow-release-1-0-1"))
            self.assertTrue(Path(str(summary["worktree_path"])).is_dir())
            self.assertTrue(str(summary["commit_sha"]))
            worktree_root = Path(str(summary["worktree_path"]))
            head_subject = self.git(worktree_root, "log", "-1", "--format=%s").stdout.strip()
            self.assertEqual(summary["commit_message"], head_subject)
            remote_heads = self.git(repo_root, "ls-remote", "--heads", "origin").stdout
            self.assertIn("refs/heads/main", remote_heads)
            self.assertNotIn("refs/heads/codex/workflow-release-1-0-1", remote_heads)

    def test_submit_release_to_repo_via_worktree_commit_supports_dirty_primary_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            self.bootstrap_managed_repo(workflow_root, repo_root, repo_id="TempRepo", installed_version="1.0.0")
            self.publish_temp_release(workflow_root, "1.0.1")
            readme_path = repo_root / "README.md"
            readme_path.write_text(readme_path.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")

            summary = submit_release_to_repo_via_worktree_commit(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("committed", summary["action"])
            status_output = self.git(repo_root, "status", "--short").stdout
            self.assertIn("README.md", status_output)

    def test_submit_release_to_repo_via_worktree_commit_cleans_up_noop_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            self.bootstrap_managed_repo(workflow_root, repo_root, repo_id="TempRepo", installed_version="1.0.0")
            managed_script = repo_root / ".git_scripts" / "new_branch.sh"
            managed_script.write_text(
                managed_script.read_text(encoding="utf-8") + "\n# local drift\n",
                encoding="utf-8",
            )

            summary = submit_release_to_repo_via_worktree_commit(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("noop-cleanup", summary["action"])
            self.assertEqual("drift", summary["status_before"])
            self.assertFalse(Path(str(summary["worktree_path"])).exists())
            branch_list = self.git(repo_root, "branch", "--list", "codex/workflow-release-1-0-0").stdout.strip()
            self.assertEqual("", branch_list)

    def test_submit_release_to_repo_via_worktree_commit_reports_existing_branch_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)

            repo_root = temp_root / "TempRepo"
            self.bootstrap_managed_repo(workflow_root, repo_root, repo_id="TempRepo", installed_version="1.0.0")
            self.publish_temp_release(workflow_root, "1.0.1")
            self.git(repo_root, "branch", "codex/workflow-release-1-0-1")

            summary = submit_release_to_repo_via_worktree_commit(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("failed", summary["action"])
            self.assertIn("Branch already exists locally", str(summary["error"]))

    def test_apply_downstreams_continues_after_failure_and_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            self.copy_workflow_repo(workflow_root)
            shutil.rmtree(workflow_root / "repos")
            (workflow_root / "repos").mkdir(parents=True, exist_ok=True)
            write_json(workflow_root / ".workflow-kit" / "source.json", {"repo_id": "WorkflowRepo"})
            self.write_named_repo_config(
                workflow_root,
                workflow_root,
                repo_id="WorkflowRepo",
                default_branch="main",
            )

            good_repo_root = temp_root / "GoodRepo"
            bad_repo_root = temp_root / "BadRepo"
            self.bootstrap_managed_repo(workflow_root, good_repo_root, repo_id="GoodRepo", installed_version="1.0.0")
            self.bootstrap_managed_repo(workflow_root, bad_repo_root, repo_id="BadRepo", installed_version="1.0.0")

            self.publish_release_for_repo_ids(workflow_root, "1.0.1", ["WorkflowRepo", "GoodRepo", "BadRepo"])
            missing_script = bad_repo_root / ".git_scripts" / "new_worktree.sh"
            missing_script.unlink()

            result = subprocess.run(
                ["python3", str(workflow_root / "scripts" / "apply_downstreams.py")],
                cwd=workflow_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(1, result.returncode)
            payload = json.loads(result.stdout)
            self.assertEqual(2, payload["processed_repo_count"])
            self.assertEqual(1, payload["failed_repo_count"])
            actions = {entry["repo_id"]: entry["action"] for entry in payload["repositories"]}
            self.assertEqual("committed", actions["GoodRepo"])
            self.assertEqual("failed", actions["BadRepo"])


if __name__ == "__main__":
    unittest.main()
