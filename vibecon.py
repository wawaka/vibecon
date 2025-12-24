#!/usr/bin/env python3

import subprocess
import os
import sys
import hashlib
import argparse
import json
import tempfile
import asyncio
from pathlib import Path

# Global configuration
IMAGE_NAME = "vibecon:latest"


# ============================================================================
# Config file support
# ============================================================================

def load_config(config_path):
    """Load JSON config file, return empty dict if not found or invalid."""
    path = os.path.expanduser(config_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}")
        sys.exit(1)


def get_merged_config(project_root):
    """Load and merge global + project configs."""
    global_cfg = load_config("~/.vibecon.json")
    project_cfg = load_config(os.path.join(project_root, ".vibecon.json"))

    return {
        "volumes": {**global_cfg.get("volumes", {}), **project_cfg.get("volumes", {})},
        "mounts": global_cfg.get("mounts", []) + project_cfg.get("mounts", []),
    }


def is_named_volume(source):
    """Check if source is a named volume (not a path)."""
    return not (source.startswith('./') or
                source.startswith('../') or
                source.startswith('~/') or
                source.startswith('/'))


def parse_mount(mount_spec, project_root, container_name, declared_volumes):
    """Parse mount spec into docker -v argument.

    Supports:
    - Anonymous volumes: "/container/path" (no colon)
    - Bind mounts: "./src:/dst" or "/src:/dst" or "~/src:/dst"
    - Named volumes: "volname:/dst" (local) or global if declared with {"global": true}
    - Long syntax: {"source": "...", "target": "...", "read_only": bool}
    """
    if isinstance(mount_spec, str):
        if ":" not in mount_spec:
            # Anonymous volume: "/container/path"
            return mount_spec
        parts = mount_spec.split(":")
        source = parts[0]
        target = parts[1]
        read_only = len(parts) > 2 and parts[2] == "ro"
    else:
        source = mount_spec.get("source")
        target = mount_spec["target"]
        read_only = mount_spec.get("read_only", False)
        if source is None:
            # Anonymous volume in long syntax
            return target

    if is_named_volume(source):
        # Named volume - check if global or local
        if source not in declared_volumes:
            print(f"Warning: volume '{source}' used but not declared in 'volumes'")
            # Default to local if undeclared
            volume_name = f"{container_name}_{source}"
        elif declared_volumes[source].get("global", False):
            # Global volume - use name as-is
            volume_name = source
        else:
            # Local volume - prefix with container name
            volume_name = f"{container_name}_{source}"
        mount_arg = f"{volume_name}:{target}"
    else:
        # Bind mount - resolve path
        resolved = os.path.expanduser(source)
        if not os.path.isabs(resolved):
            resolved = os.path.normpath(os.path.join(project_root, resolved))
        if not os.path.exists(resolved):
            print(f"Warning: mount source does not exist: {resolved}")
        mount_arg = f"{resolved}:{target}"

    if read_only:
        mount_arg += ":ro"

    return mount_arg


# DEFAULT_COMMAND = ["zsh"]
DEFAULT_COMMAND = ["claude", "--dangerously-skip-permissions"]

def install_symlink(simulate_path_missing=False):
    """Install symlink to ~/.local/bin/vibecon"""
    # ANSI color codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"

    script_path = Path(__file__).resolve()
    install_dir = Path.home() / ".local" / "bin"
    symlink_path = install_dir / "vibecon"

    # Create a display version with $HOME substitution
    home_str = str(Path.home())
    install_dir_str = str(install_dir)
    if install_dir_str.startswith(home_str):
        install_dir_display = "$HOME" + install_dir_str[len(home_str):]
    else:
        install_dir_display = install_dir_str

    # Create install directory if it doesn't exist
    install_dir.mkdir(parents=True, exist_ok=True)

    # Check if symlink already exists and points to the correct target
    already_installed = False
    if symlink_path.is_symlink() and symlink_path.resolve() == script_path:
        already_installed = True
        print(f"{GREEN}{BOLD}Already installed:{RESET} {CYAN}{symlink_path}{RESET} -> {BLUE}{script_path}{RESET}")
    else:
        # Remove existing symlink if it exists but points elsewhere
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()

        # Create symlink
        symlink_path.symlink_to(script_path)
        print(f"{GREEN}Installed:{RESET} {CYAN}{symlink_path}{RESET} -> {BLUE}{script_path}{RESET}")

    # Check if install directory is in PATH
    path_env = os.environ.get("PATH", "")
    if simulate_path_missing or install_dir_str not in path_env.split(os.pathsep):
        # Detect user's shell
        shell_path = os.environ.get("SHELL", "")
        shell_name = os.path.basename(shell_path) if shell_path else "unknown"

        # Determine config file and export syntax based on shell
        if shell_name == "zsh":
            config_file = "~/.zshrc"
            export_cmd = f'export PATH="{install_dir_display}:$PATH"'
        elif shell_name == "bash":
            config_file = "~/.bashrc"
            export_cmd = f'export PATH="{install_dir_display}:$PATH"'
        elif shell_name == "fish":
            config_file = "~/.config/fish/config.fish"
            export_cmd = f'set -gx PATH "{install_dir_display}" $PATH'
        elif shell_name in ["tcsh", "csh"]:
            config_file = "~/.cshrc"
            export_cmd = f'setenv PATH "{install_dir_display}:$PATH"'
        else:
            config_file = "~/.profile"
            export_cmd = f'export PATH="{install_dir_display}:$PATH"'

        # Print large banner warning with colors
        print(f"\n{RED}{BOLD}{'=' * 70}")
        print(f"  ⚠️  WARNING: PATH CUSTOMIZATION REQUIRED")
        print(f"{'=' * 70}{RESET}")
        print(f"\n  {YELLOW}{BOLD}{install_dir_display}{RESET} {RED}{BOLD}is NOT in your PATH!{RESET}\n")
        print(f"  You must add it to your PATH to use {CYAN}{BOLD}'vibecon'{RESET} by name.")
        print(f"\n{BLUE}{'─' * 70}{RESET}")
        print(f"  {MAGENTA}Detected shell:{RESET} {BOLD}{shell_name}{RESET}")
        print(f"{BLUE}{'─' * 70}{RESET}")
        print(f"\n  Add to PATH {GREEN}permanently{RESET}:")
        print(f"    {GREEN}echo '{export_cmd}' >> {config_file}{RESET}")
        print(f"    {GREEN}source {config_file}{RESET}")
        print(f"\n{RED}{BOLD}{'=' * 70}{RESET}\n")
    else:
        print(f"\n{GREEN}{BOLD}✓{RESET} {GREEN}You can now use vibecon by its name:{RESET} {CYAN}{BOLD}vibecon{RESET}")

def uninstall_symlink():
    """Uninstall symlink from ~/.local/bin/vibecon"""
    symlink_path = Path.home() / ".local" / "bin" / "vibecon"

    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()
        print(f"Uninstalled: {symlink_path}")
    else:
        print(f"Symlink not found: {symlink_path}")

def is_container_running(container_name):
    """Check if container is running"""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    return result.returncode == 0 and result.stdout.strip() == "true"

def container_exists(container_name):
    """Check if container exists (in any state: running, stopped, dead, etc.)"""
    result = subprocess.run(
        ["docker", "inspect", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0

def restart_container(container_name):
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

def stop_container(container_name):
    """Stop the container (can be restarted later)"""
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

def destroy_container(container_name):
    """Destroy and remove the container permanently"""
    print(f"Destroying container '{container_name}'...")
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Container destroyed.")

def find_vibecon_root():
    """Find the vibecon root directory (parent of vibecon.py where Dockerfile is)"""
    # Resolve symlink to find actual script location
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    dockerfile_path = script_dir / "Dockerfile"

    if dockerfile_path.exists():
        return str(script_dir)
    return None

def generate_container_name(workspace_path):
    """Generate container name based on workspace path"""
    # Create full hash from the workspace path
    path_hash = hashlib.md5(workspace_path.encode()).hexdigest()[:8]

    # Sanitize the path for use in container name
    # Remove leading slash and replace special chars with hyphens
    sanitized_path = workspace_path.lstrip('/').replace('/', '-').replace('_', '-').lower()

    return f"vibecon-{sanitized_path}-{path_hash}"

def image_exists(image_name):
    """Check if Docker image exists"""
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0

async def get_npm_package_version_async(package_name, short_name):
    """Get the latest version of an npm package asynchronously"""
    proc = await asyncio.create_subprocess_exec(
        "npm", "view", package_name, "version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return stdout.decode().strip()
    else:
        print(f"Warning: Failed to get {short_name} version from npm")
        return None


def get_all_versions():
    """Get versions of all 3 AI CLI tools from npm concurrently"""
    print("Checking latest versions from npm...")

    packages = [
        ("@anthropic-ai/claude-code", "cc", "Claude Code"),
        ("@google/gemini-cli", "g", "Gemini CLI"),
        ("@openai/codex", "oac", "OpenAI Codex"),
    ]

    async def fetch_all():
        tasks = [get_npm_package_version_async(pkg, short) for pkg, short, _ in packages]
        return await asyncio.gather(*tasks)

    results = asyncio.run(fetch_all())

    versions = {}
    for (_, short_name, display_name), version in zip(packages, results):
        if version:
            versions[short_name] = version
            print(f"  {display_name}: {version}")
        else:
            versions[short_name] = "latest"
            print(f"  {display_name}: latest (failed to fetch)")

    return versions


def make_composite_tag(versions):
    """Create composite tag from versions: cc{ver}_g{ver}_oac{ver}"""
    return f"cc{versions['cc']}_g{versions['g']}_oac{versions['oac']}"

def get_host_timezone():
    """Get the host system timezone"""
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

def get_git_user_info():
    """Get git user.name and user.email from host"""
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

def build_image(vibecon_root, image_name, versions=None):
    """Build the Docker image with all 3 AI CLI tools"""
    if versions is None:
        versions = {"cc": "latest", "g": "latest", "oac": "latest"}

    composite_tag = make_composite_tag(versions)
    print(f"Building image with composite tag: {composite_tag}")

    # Build command with all version build args
    build_cmd = [
        "docker", "build",
        "--build-arg", f"CLAUDE_CODE_VERSION={versions['cc']}",
        "--build-arg", f"GEMINI_CLI_VERSION={versions['g']}",
        "--build-arg", f"OPENAI_CODEX_VERSION={versions['oac']}",
        "-t", image_name,
        "-t", f"vibecon:{composite_tag}"
    ]

    print(f"Tagging as: {image_name} and vibecon:{composite_tag}")

    build_cmd.append(".")

    build_result = subprocess.run(build_cmd, cwd=vibecon_root)
    if build_result.returncode != 0:
        print("Failed to build image")
        sys.exit(1)

    return composite_tag

def sync_claude_config(container_name):
    """Sync Claude config to container: statusLine section + referenced files + CLAUDE.md"""
    claude_dir = Path.home() / ".claude"
    container_claude_dir = "/home/node/.claude"
    settings_file = claude_dir / "settings.json"
    claude_md_file = claude_dir / "CLAUDE.md"

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
        ["docker", "exec", container_name, "mkdir", "-p", container_claude_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Handle CLAUDE.md sync: copy if exists locally, remove from container if not
    if claude_md_file.exists():
        files_to_copy.append(claude_md_file)
    else:
        # Remove CLAUDE.md from container if it doesn't exist locally
        subprocess.run(
            ["docker", "exec", container_name, "rm", "-f", f"{container_claude_dir}/CLAUDE.md"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # Copy files using tar if we have any
    if files_to_copy:
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
                ["docker", "exec", "-i", container_name, "tar", "-xf", "-", "-C", container_claude_dir],
                stdin=tar_create.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            tar_create.wait()
            if tar_extract.returncode != 0:
                print(f"Warning: Failed to copy files: {tar_extract.stderr.decode()}")

    # Write container settings.json if we have any settings to write
    if container_settings:
        settings_json = json.dumps(container_settings, indent=2)
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             f"cat > {container_claude_dir}/settings.json << 'EOFCONFIG'\n{settings_json}\nEOFCONFIG"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

    # Fix ownership for node user
    subprocess.run(
        ["docker", "exec", "-u", "root", container_name, "chown", "-R", "node:node", container_claude_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def start_container(cwd, container_name, image_name, config=None):
    """Start the container in detached mode"""
    if config is None:
        config = {"volumes": {}, "mounts": []}

    host_term = os.environ.get("TERM", "xterm-256color")
    container_hostname = "vibecon"

    # Get git user info from host
    git_user_name, git_user_email = get_git_user_info()
    if git_user_name:
        print(f"Configuring git user: {git_user_name} <{git_user_email}>")

    # Get host timezone
    host_timezone = get_host_timezone()
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
    declared_volumes = config.get("volumes", {})
    for mount_spec in config.get("mounts", []):
        mount_arg = parse_mount(mount_spec, cwd, container_name, declared_volumes)
        docker_cmd.extend(["-v", mount_arg])

    # Add image name
    docker_cmd.append(image_name)

    # Start container detached with sleep infinity to keep it running
    run_result = subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if run_result.returncode != 0:
        print(f"Failed to start container: {run_result.stderr.decode()}")
        sys.exit(1)

def ensure_container_running(cwd, vibecon_root, container_name, image_name, config=None):
    """Ensure container is running"""
    if is_container_running(container_name):
        return  # Already running, nothing to do

    # Container is not running - check if it exists (stopped/dead)
    if container_exists(container_name):
        # Try to restart the stopped container
        if restart_container(container_name):
            return  # Successfully restarted
        # Restart failed, remove and recreate
        print("Restart failed, removing container and creating a new one...")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # Build image only if it doesn't exist
    if not image_exists(image_name):
        print(f"Image '{image_name}' not found, building...")
        build_image(vibecon_root, image_name)
    start_container(cwd, container_name, image_name, config)

def main():
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

    args = parser.parse_args()

    # Handle install flag - install symlink and exit
    if args.install:
        install_symlink()
        sys.exit(0)

    # Handle install test flag - install symlink with PATH warning simulation and exit
    if args.install_test:
        install_symlink(simulate_path_missing=True)
        sys.exit(0)

    # Handle uninstall flag - uninstall symlink and exit
    if args.uninstall:
        uninstall_symlink()
        sys.exit(0)

    cwd = os.getcwd()
    vibecon_root = find_vibecon_root()

    if not vibecon_root:
        print("Error: Could not find Dockerfile in vibecon.py directory")
        sys.exit(1)

    container_name = generate_container_name(cwd)

    # Load config files
    config = get_merged_config(cwd)

    # Handle build flag - check versions and build only if needed
    if args.build or args.force_build:
        versions = get_all_versions()
        composite_tag = make_composite_tag(versions)
        versioned_image = f"vibecon:{composite_tag}"

        if image_exists(versioned_image) and not args.force_build:
            print(f"\nImage already exists: {versioned_image}")
            print("No rebuild needed - all versions are up to date.")
            print("Use -B/--force-build to rebuild anyway.")
        else:
            if args.force_build and image_exists(versioned_image):
                print(f"\nForce rebuild requested...")
            else:
                print(f"\nNew versions detected, building image...")
            build_image(vibecon_root, IMAGE_NAME, versions)
            print(f"\nBuild complete! Image tagged as:")
            print(f"  - {IMAGE_NAME}")
            print(f"  - {versioned_image}")
        sys.exit(0)

    # Handle stop flag - stop the container and exit
    if args.stop:
        stop_container(container_name)
        sys.exit(0)

    # Handle destroy flag - destroy the container and exit
    if args.destroy:
        destroy_container(container_name)
        sys.exit(0)

    # Get command to execute (use default if not specified)
    command = args.command if args.command else DEFAULT_COMMAND

    # Ensure container is running
    ensure_container_running(cwd, vibecon_root, container_name, IMAGE_NAME, config)

    # Sync claude config before exec
    sync_claude_config(container_name)

    # Execute command in container
    host_term = os.environ.get("TERM", "xterm-256color")
    host_timezone = get_host_timezone()

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

    sys.exit(exec_result.returncode)

if __name__ == "__main__":
    main()
