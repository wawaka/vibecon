"""Claude configuration synchronization for Vibecon."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any


class ClaudeConfigSync:
    """Handles synchronization of Claude configuration to containers."""
    
    def __init__(self, container_name: str):
        self.container_name = container_name
        self.claude_dir = Path.home() / ".claude"
        self.container_claude_dir = "/home/node/.claude"
    
    def sync_claude_config(self) -> None:
        """Sync Claude config to container: statusLine section + referenced files + CLAUDE.md + commands dir."""
        settings_file = self.claude_dir / "settings.json"
        claude_md_file = self.claude_dir / "CLAUDE.md"

        # Track files to copy and whether we need to do anything
        files_to_copy = []
        container_settings = {}

        # Parse settings.json if it exists
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    settings = json.load(f)

                # Extract statusLine section if present
                if "statusLine" in settings:
                    container_settings["statusLine"] = settings["statusLine"]

                    # If statusLine has a command, add that file to copy list
                    if "command" in settings["statusLine"]:
                        cmd_path = settings["statusLine"]["command"]
                        # Expand ~ to home directory
                        if cmd_path.startswith("~"):
                            cmd_path = str(Path.home()) + cmd_path[1:]
                        cmd_file = Path(cmd_path)
                        if cmd_file.exists():
                            files_to_copy.append(cmd_file)

            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to parse settings.json: {e}")

        # Ensure container directory exists
        subprocess.run(
            ["docker", "exec", self.container_name, "mkdir", "-p", self.container_claude_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Handle CLAUDE.md sync: copy if exists locally, remove from container if not
        if claude_md_file.exists():
            files_to_copy.append(claude_md_file)
        else:
            # Remove CLAUDE.md from container if it doesn't exist locally
            subprocess.run(
                ["docker", "exec", self.container_name, "rm", "-f", f"{self.container_claude_dir}/CLAUDE.md"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        # Handle commands directory sync (may be a symlink)
        self._sync_commands_directory()

        # Copy files using tar if we have any
        if files_to_copy:
            self._copy_files_to_container(files_to_copy)

        # Write container settings.json if we have any settings to write
        if container_settings:
            self._write_container_settings(container_settings)

        # Fix ownership for node user
        subprocess.run(
            ["docker", "exec", "-u", "root", self.container_name, "chown", "-R", "node:node", self.container_claude_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def _sync_commands_directory(self) -> None:
        """Handle commands directory sync (may be a symlink)."""
        commands_dir = self.claude_dir / "commands"
        commands_source = None
        if commands_dir.exists():
            # Resolve symlink if it is one
            commands_source = commands_dir.resolve()
            if not commands_source.is_dir():
                commands_source = None

        if commands_source:
            # Remove existing commands directory to ensure clean sync (no stale files)
            subprocess.run(
                ["docker", "exec", self.container_name, "rm", "-rf", f"{self.container_claude_dir}/commands"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Create fresh commands directory
            subprocess.run(
                ["docker", "exec", self.container_name, "mkdir", "-p", f"{self.container_claude_dir}/commands"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Copy commands directory using tar
            tar_create = subprocess.Popen(
                ["tar", "-cf", "-", "."],
                cwd=str(commands_source),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            tar_extract = subprocess.run(
                ["docker", "exec", "-i", self.container_name, "tar", "-xf", "-", "-C", f"{self.container_claude_dir}/commands"],
                stdin=tar_create.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            tar_create.wait()
            if tar_extract.returncode != 0:
                print(f"Warning: Failed to copy commands directory: {tar_extract.stderr.decode()}")
        else:
            # Remove commands directory from container if it doesn't exist locally
            subprocess.run(
                ["docker", "exec", self.container_name, "rm", "-rf", f"{self.container_claude_dir}/commands"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def _copy_files_to_container(self, files_to_copy: List[Path]) -> None:
        """Copy files to container using tar."""
        # Build tar with files, preserving just the filename (not full path)
        # We need to handle files from different directories
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            for src_file in files_to_copy:
                # Copy to temp dir with just the filename
                dest = tmpdir_path / src_file.name
                dest.write_bytes(src_file.read_bytes())
                # Preserve executable bit
                if os.access(src_file, os.X_OK):
                    dest.chmod(dest.stat().st_mode | 0o111)

            # Tar and copy all files at once
            tar_create = subprocess.Popen(
                ["tar", "-cf", "-", "."],
                cwd=str(tmpdir_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            tar_extract = subprocess.run(
                ["docker", "exec", "-i", self.container_name, "tar", "-xf", "-", "-C", self.container_claude_dir],
                stdin=tar_create.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            tar_create.wait()
            if tar_extract.returncode != 0:
                print(f"Warning: Failed to copy files: {tar_extract.stderr.decode()}")

    def _write_container_settings(self, container_settings: Dict[str, Any]) -> None:
        """Write settings.json to container."""
        settings_json = json.dumps(container_settings, indent=2)
        subprocess.run(
            ["docker", "exec", self.container_name, "sh", "-c",
             f"cat > {self.container_claude_dir}/settings.json << 'EOFCONFIG'\n{settings_json}\nEOFCONFIG"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )