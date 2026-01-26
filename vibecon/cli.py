"""Main CLI interface for Vibecon."""

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import ConfigManager
from .docker_manager import DockerManager
from .version_manager import VersionManager
from .installation import InstallationManager
from .claude_sync import ClaudeConfigSync


# Constants
DEFAULT_COMMAND = ["claude", "--dangerously-skip-permissions"]
IMAGE_NAME = "vibecon:latest"


class VibeconCLI:
    """Main CLI orchestrator for Vibecon."""
    
    def __init__(self):
        self.docker_manager = DockerManager(IMAGE_NAME)
        self.version_manager = VersionManager()
        self.installation_manager = InstallationManager()
    
    def run(self) -> None:
        """Run the main CLI application."""
        args = self._parse_args()
        
        # Handle install flag - install symlink and exit
        if args.install:
            self.installation_manager.install_symlink()
            sys.exit(0)

        # Handle install test flag - install symlink with PATH warning simulation and exit
        if args.install_test:
            self.installation_manager.install_symlink(simulate_path_missing=True)
            sys.exit(0)

        # Handle uninstall flag - uninstall symlink and exit
        if args.uninstall:
            self.installation_manager.uninstall_symlink()
            sys.exit(0)

        # For other commands, we need to be in a project directory
        cwd = os.getcwd()
        vibecon_root = self._find_vibecon_root()

        if not vibecon_root:
            print("Error: Could not find Dockerfile in vibecon.py directory")
            sys.exit(1)

        container_name = self._generate_container_name(cwd)
        config_manager = ConfigManager(cwd)
        config = config_manager.get_merged_config()

        # Handle build flag - check versions and build only if needed
        if args.build or args.force_build:
            self._handle_build_command(vibecon_root, args.force_build)
            sys.exit(0)

        # Handle stop flag - stop the container and exit
        if args.stop:
            self.docker_manager.stop_container(container_name)
            sys.exit(0)

        # Handle destroy flag - destroy the container and exit
        if args.destroy:
            self.docker_manager.destroy_container(container_name)
            sys.exit(0)

        # Get command to execute (use default if not specified)
        command = args.command if args.command else DEFAULT_COMMAND

        # Ensure container is running
        self.docker_manager.ensure_container_running(
            cwd, vibecon_root, container_name, config, self.version_manager.build_image
        )

        # Sync claude config before exec
        claude_sync = ClaudeConfigSync(container_name)
        claude_sync.sync_claude_config()

        # Execute command in container
        exit_code = self.docker_manager.exec_in_container(container_name, command)
        sys.exit(exit_code)
    
    def _parse_args(self) -> argparse.Namespace:
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(
            description="vibecon - Persistent Docker container environment",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"""
 Examples:
  %(prog)s                    # Start "{' '.join(DEFAULT_COMMAND)}" in container
  %(prog)s zsh                # Run zsh in container
  %(prog)s claude             # Run Claude Code in container
  %(prog)s gemini             # Run Gemini CLI in container
  %(prog)s codex              # Run OpenAI Codex in container
  %(prog)s -b                 # Check versions and rebuild if updated
  %(prog)s -B                 # Force rebuild regardless of versions
  %(prog)s -k                 # Stop container (can be restarted)
  %(prog)s -K                 # Destroy container permanently
 """
        )

        parser.add_argument(
            "-i", "--install",
            action="store_true",
            help="install symlink to ~/.local/bin/vibecon"
        )

        parser.add_argument(
            "-I",
            action="store_true",
            dest="install_test",
            help=argparse.SUPPRESS  # Hidden flag for testing PATH warning
        )

        parser.add_argument(
            "-u", "--uninstall",
            action="store_true",
            help="uninstall symlink from ~/.local/bin/vibecon"
        )

        parser.add_argument(
            "-k", "--stop",
            action="store_true",
            help="stop the container for current workspace (can be restarted)"
        )

        parser.add_argument(
            "-K", "--destroy",
            action="store_true",
            help="destroy and remove the container permanently"
        )

        parser.add_argument(
            "-b", "--build",
            action="store_true",
            help="rebuild the Docker image (skips if versions unchanged)"
        )

        parser.add_argument(
            "-B", "--force-build",
            action="store_true",
            help="force rebuild even if image exists"
        )

        parser.add_argument(
            "command",
            nargs="*",
            help="command to execute in container (default: zsh)"
        )

        return parser.parse_args()
    
    def _find_vibecon_root(self) -> Optional[str]:
        """Find the vibecon root directory (parent of vibecon.py where Dockerfile is)."""
        # Resolve symlink to find actual script location
        script_path = Path(__file__).resolve()
        script_dir = script_path.parent.parent
        dockerfile_path = script_dir / "Dockerfile"

        if dockerfile_path.exists():
            return str(script_dir)
        return None
    
    def _generate_container_name(self, workspace_path: str) -> str:
        """Generate container name based on workspace path."""
        # Create full hash from the workspace path
        path_hash = hashlib.md5(workspace_path.encode()).hexdigest()[:8]

        # Sanitize the path for use in container name
        # Remove leading slash and replace special chars with hyphens
        sanitized_path = workspace_path.lstrip('/').replace('/', '-').replace('_', '-').lower()

        return f"vibecon-{sanitized_path}-{path_hash}"
    
    def _handle_build_command(self, vibecon_root: str, force_build: bool) -> None:
        """Handle the build command logic."""
        versions = self.version_manager.get_all_versions()
        composite_tag = self.version_manager.make_composite_tag(versions)
        versioned_image = f"vibecon:{composite_tag}"

        if self.docker_manager.image_exists(versioned_image) and not force_build:
            print(f"\nImage already exists: {versioned_image}")
            print("No rebuild needed - all versions are up to date.")
            print("Use -B/--force-build to rebuild anyway.")
        else:
            if force_build and self.docker_manager.image_exists(versioned_image):
                print(f"\nForce rebuild requested...")
            else:
                print(f"\nNew versions detected, building image...")
            self.version_manager.build_image(vibecon_root, IMAGE_NAME, versions)
            print(f"\nBuild complete! Image tagged as:")
            print(f"  - {IMAGE_NAME}")
            print(f"  - {versioned_image}")