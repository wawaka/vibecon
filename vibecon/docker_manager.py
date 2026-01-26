"""Docker operations management for Vibecon."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable

from .config import ConfigManager
from .mount_parser import MountParser


class DockerManager:
    """Manages Docker container operations for Vibecon."""
    
    def __init__(self, image_name: str = "vibecon:latest"):
        self.image_name = image_name
    
    def is_container_running(self, container_name: str) -> bool:
        """Check if container is running."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def container_exists(self, container_name: str) -> bool:
        """Check if container exists (in any state: running, stopped, dead, etc.)."""
        result = subprocess.run(
            ["docker", "inspect", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0

    def restart_container(self, container_name: str) -> bool:
        """Attempt to restart a stopped/dead container. Returns True if successful."""
        print(f"Found stopped container '{container_name}', attempting to restart...")
        result = subprocess.run(
            ["docker", "start", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if result.returncode == 0:
            print(f"Container '{container_name}' restarted successfully.")
            return True
        else:
            print(f"Failed to restart container: {result.stderr.decode().strip()}")
            return False

    def stop_container(self, container_name: str) -> None:
        """Stop the container (can be restarted later)."""
        print(f"Stopping container '{container_name}'...")
        result = subprocess.run(
            ["docker", "stop", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            print("Container stopped.")
        else:
            print("Container was not running.")

    def destroy_container(self, container_name: str) -> None:
        """Destroy and remove the container permanently."""
        print(f"Destroying container '{container_name}'...")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("Container destroyed.")

    def image_exists(self, image_name: str) -> bool:
        """Check if Docker image exists."""
        result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            # Only return False if it's actually "not found", not other errors
            if "no such image" in result.stderr.lower():
                return False
            # Some other error occurred - print it and exit
            print(f"Error checking image: {result.stderr.strip()}")
            sys.exit(1)
        return True

    def start_container(self, cwd: str, container_name: str, config: Optional[Dict[str, Any]] = None) -> None:
        """Start the container in detached mode."""
        if config is None:
            config = {"volumes": {}, "mounts": []}

        host_term = os.environ.get("TERM", "xterm-256color")
        container_hostname = "vibecon"

        # Get git user info from host
        git_user_name, git_user_email = self._get_git_user_info()
        if git_user_name:
            print(f"Configuring git user: {git_user_name} <{git_user_email}>")

        # Get host timezone
        host_timezone = self._get_host_timezone()
        print(f"Configuring timezone: {host_timezone}")

        print(f"Starting container '{container_name}' with {cwd} mounted at /workspace...")

        # Build docker run command
        docker_cmd = [
            "docker", "run",
            "-d",
            "--name", container_name,
            "--hostname", container_hostname,
            "-e", f"TERM={host_term}",
            "-e", "COLORTERM=truecolor",
            "-e", f"TZ={host_timezone}",
        ]

        # Add git user environment variables if available
        if git_user_name:
            docker_cmd.extend([
                "-e", f"GIT_USER_NAME={git_user_name}",
                "-e", f"GIT_USER_EMAIL={git_user_email}",
            ])

        # Add main workspace volume mount
        docker_cmd.extend(["-v", f"{cwd}:/workspace"])

        # Add extra mounts from config
        for mount_spec in config.get("mounts", []):
            mount_args = MountParser.parse_mount(mount_spec, cwd, container_name)
            docker_cmd.extend(mount_args)

        # Add image name
        docker_cmd.append(self.image_name)

        # Start container detached with sleep infinity to keep it running
        run_result = subprocess.run(
            docker_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if run_result.returncode != 0:
            print(f"Failed to start container: {run_result.stderr.decode()}")
            sys.exit(1)

    def exec_in_container(self, container_name: str, command: List[str]) -> int:
        """Execute a command in the container and return the exit code."""
        host_term = os.environ.get("TERM", "xterm-256color")
        host_timezone = self._get_host_timezone()

        exec_result = subprocess.run(
            [
                "docker", "exec",
                "-it",
                "-e", f"TERM={host_term}",
                "-e", "COLORTERM=truecolor",
                "-e", f"TZ={host_timezone}",
                container_name
            ] + command
        )
        return exec_result.returncode

    def ensure_container_running(self, cwd: str, vibecon_root: str, container_name: str,
                                config: Optional[Dict[str, Any]] = None,
                                build_image_func: Optional[Callable[[str, str, Dict[str, str]], str]] = None) -> None:
        """Ensure container is running."""
        if self.is_container_running(container_name):
            return  # Already running, nothing to do

        # Container is not running - check if it exists (stopped/dead)
        if self.container_exists(container_name):
            # Try to restart the stopped container
            if self.restart_container(container_name):
                return  # Successfully restarted
            # Restart failed, remove and recreate
            print("Restart failed, removing container and creating a new one...")
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        # Build image only if it doesn't exist
        if not self.image_exists(self.image_name):
            print(f"Image '{self.image_name}' not found, building...")
            if build_image_func:
                build_image_func(vibecon_root, self.image_name)
        self.start_container(cwd, container_name, config)

    def _get_host_timezone(self) -> str:
        """Get the host system timezone."""
        # First, try the TZ environment variable
        tz = os.environ.get("TZ")
        if tz:
            return tz

        # Try reading /etc/timezone (common on Debian/Ubuntu)
        try:
            with open("/etc/timezone", "r") as f:
                tz = f.read().strip()
                if tz:
                    return tz
        except (FileNotFoundError, PermissionError):
            pass

        # Try to get timezone from timedatectl (systemd-based systems)
        try:
            result = subprocess.run(
                ["timedatectl", "show", "-p", "Timezone", "--value"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            if result.returncode == 0:
                tz = result.stdout.strip()
                if tz:
                    return tz
        except FileNotFoundError:
            pass

        # Fallback: try to determine from /etc/localtime symlink
        try:
            localtime_path = Path("/etc/localtime")
            if localtime_path.is_symlink():
                target = localtime_path.resolve()
                # Extract timezone from path like /usr/share/zoneinfo/America/New_York
                parts = target.parts
                if "zoneinfo" in parts:
                    zoneinfo_idx = parts.index("zoneinfo")
                    if len(parts) > zoneinfo_idx + 1:
                        tz = "/".join(parts[zoneinfo_idx + 1:])
                        return tz
        except (FileNotFoundError, PermissionError):
            pass

        # If all else fails, return UTC as default
        return "UTC"

    def _get_git_user_info(self) -> Tuple[str, str]:
        """Get git user.name and user.email from host."""
        user_name = ""
        user_email = ""

        # Get git user.name
        result = subprocess.run(
            ["git", "config", "--global", "user.name"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        if result.returncode == 0:
            user_name = result.stdout.strip()

        # Get git user.email
        result = subprocess.run(
            ["git", "config", "--global", "user.email"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        if result.returncode == 0:
            user_email = result.stdout.strip()

        return user_name, user_email