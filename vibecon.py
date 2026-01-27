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
        "mounts": global_cfg.get("mounts", []) + project_cfg.get("mounts", []),
    }


def parse_mount(mount_spec, project_root, container_name):
    """Parse mount spec into docker mount arguments.

    Returns a list of docker arguments, e.g., ["-v", "..."] or ["--mount", "..."]

    All mounts must be objects with explicit type. Supported types:

    1. type="bind" - Bind mount from host to container
       Required: type, source, target
       Optional: read_only (bool), selinux ("z" or "Z")

    2. type="volume" - Named Docker volume
       Required: type, source (volume name), target
       Optional: read_only (bool), uid (int), gid (int), selinux ("z" or "Z"), global (bool)

    3. type="anonymous" - Anonymous Docker volume
       Required: type, target
       Optional: read_only (bool), uid (int), gid (int)
    """
    if isinstance(mount_spec, str):
        print(f"Error: Mount must be an object with explicit 'type' field, got string: {mount_spec}")
        sys.exit(1)

    if not isinstance(mount_spec, dict):
        print(f"Error: Mount must be an object, got: {type(mount_spec).__name__}")
        sys.exit(1)

    mount_type = mount_spec.get("type")
    if not mount_type:
        print(f"Error: Mount missing required 'type' field: {mount_spec}")
        sys.exit(1)

    target = mount_spec.get("target")
    if not target:
        print(f"Error: Mount missing required 'target' field: {mount_spec}")
        sys.exit(1)

    read_only = mount_spec.get("read_only", False)
    selinux = mount_spec.get("selinux")  # "z" or "Z"

    if mount_type == "anonymous":
        # Anonymous volume - just needs target path
        uid = mount_spec.get("uid")
        gid = mount_spec.get("gid")

        if uid is not None or gid is not None:
            # Use --mount syntax with tmpfs-backed volume for uid/gid support
            mount_opts = []
            if uid is not None:
                mount_opts.append(f"uid={uid}")
            if gid is not None:
                mount_opts.append(f"gid={gid}")
            driver_opts = f"o={','.join(mount_opts)}"

            mount_parts = [
                "type=volume",
                f"target={target}",
                "volume-opt=type=tmpfs",
                "volume-opt=device=tmpfs",
                f'"volume-opt={driver_opts}"',
            ]
            if read_only:
                mount_parts.append("readonly")
            return ["--mount", ",".join(mount_parts)]
        else:
            return ["-v", target]

    elif mount_type == "bind":
        # Bind mount - requires source path
        source = mount_spec.get("source")
        if not source:
            print(f"Error: Bind mount missing required 'source' field: {mount_spec}")
            sys.exit(1)

        # Resolve source path
        resolved = os.path.expanduser(source)
        if not os.path.isabs(resolved):
            resolved = os.path.normpath(os.path.join(project_root, resolved))
        if not os.path.exists(resolved):
            print(f"Warning: bind mount source does not exist: {resolved}")

        # uid/gid not supported for bind mounts
        if mount_spec.get("uid") or mount_spec.get("gid"):
            print(f"Warning: uid/gid options ignored for bind mount (not supported by Docker)")

        mount_arg = f"{resolved}:{target}"
        suffix_opts = []
        if read_only:
            suffix_opts.append("ro")
        if selinux:
            suffix_opts.append(selinux)
        if suffix_opts:
            mount_arg += ":" + ",".join(suffix_opts)
        return ["-v", mount_arg]

    elif mount_type == "volume":
        # Named volume - requires source (volume name)
        source = mount_spec.get("source")
        if not source:
            print(f"Error: Volume mount missing required 'source' field: {mount_spec}")
            sys.exit(1)

        # Determine volume name based on global flag
        if mount_spec.get("global", False):
            volume_name = source
        else:
            # Local volume - prefix with container name
            volume_name = f"{container_name}_{source}"

        uid = mount_spec.get("uid")
        gid = mount_spec.get("gid")

        # If uid/gid specified, use --mount syntax with tmpfs-backed volume
        if uid is not None or gid is not None:
            mount_opts = []
            if uid is not None:
                mount_opts.append(f"uid={uid}")
            if gid is not None:
                mount_opts.append(f"gid={gid}")
            driver_opts = f"o={','.join(mount_opts)}"

            mount_parts = [
                "type=volume",
                f"source={volume_name}",
                f"target={target}",
                "volume-opt=type=tmpfs",
                "volume-opt=device=tmpfs",
                f'"volume-opt={driver_opts}"',
            ]
            if read_only:
                mount_parts.append("readonly")
            return ["--mount", ",".join(mount_parts)]
        else:
            # Simple -v syntax
            mount_arg = f"{volume_name}:{target}"
            suffix_opts = []
            if read_only:
                suffix_opts.append("ro")
            if selinux:
                suffix_opts.append(selinux)
            if suffix_opts:
                mount_arg += ":" + ",".join(suffix_opts)
            return ["-v", mount_arg]

    else:
        print(f"Error: Unknown mount type '{mount_type}'. Must be 'bind', 'volume', or 'anonymous'")
        sys.exit(1)


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


async def get_go_version_async():
    """Get the latest stable Go version from golang.org"""
    proc = await asyncio.create_subprocess_exec(
        "curl", "-s", "https://go.dev/dl/?mode=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        try:
            releases = json.loads(stdout.decode())
            # First stable release in the list
            for release in releases:
                if release.get("stable", False):
                    # Version is like "go1.24.2", strip the "go" prefix
                    return release["version"].lstrip("go")
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
    print("Warning: Failed to get Go version from golang.org")
    return None


def get_all_versions():
    """Get versions of all AI CLI tools from npm and Go from golang.org concurrently"""
    print("Checking latest versions...")

    packages = [
        ("@google/gemini-cli", "g", "Gemini CLI"),
        ("@openai/codex", "oac", "OpenAI Codex"),
    ]

    async def fetch_all():
        npm_tasks = [get_npm_package_version_async(pkg, short) for pkg, short, _ in packages]
        go_task = get_go_version_async()
        all_tasks = npm_tasks + [go_task]
        return await asyncio.gather(*all_tasks)

    results = asyncio.run(fetch_all())

    # npm package results
    npm_results = results[:-1]
    go_result = results[-1]

    versions = {}
    for (_, short_name, display_name), version in zip(packages, npm_results):
        if version:
            versions[short_name] = version
            print(f"  {display_name}: {version}")
        else:
            versions[short_name] = "latest"
            print(f"  {display_name}: latest (failed to fetch)")

    # Go version
    if go_result:
        versions["go"] = go_result
        print(f"  Go: {go_result}")
    else:
        versions["go"] = "1.24.2"  # fallback
        print(f"  Go: 1.24.2 (failed to fetch, using fallback)")

    return versions


def make_composite_tag(versions):
    """Create composite tag from versions: g{ver}_oac{ver}_go{ver}"""
    return f"g{versions['g']}_oac{versions['oac']}_go{versions['go']}"

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

def detect_worktree(workspace_path):
    """Detect if workspace is a git worktree, return main .git path if so.

    In a worktree, .git is a file containing 'gitdir: /path/to/main/.git/worktrees/name'.
    We need to mount the main .git directory so git operations work inside the container.

    Returns:
        str: Path to main .git directory if this is a worktree, None otherwise.
    """
    git_path = os.path.join(workspace_path, ".git")

    # If .git is a directory, this is a normal repo (not a worktree)
    if os.path.isdir(git_path):
        return None

    # If .git is a file, parse it to find the main repo's .git directory
    if os.path.isfile(git_path):
        try:
            with open(git_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content.startswith("gitdir:"):
                # Parse: gitdir: /path/to/main/.git/worktrees/name
                gitdir = content.split(":", 1)[1].strip()
                # Resolve to absolute path (handles relative paths)
                gitdir = os.path.abspath(os.path.join(workspace_path, gitdir))
                # Go up from .git/worktrees/name to .git
                # gitdir points to: main-repo/.git/worktrees/worktree-name
                # We want: main-repo/.git
                if "/worktrees/" in gitdir:
                    main_git = gitdir.rsplit("/worktrees/", 1)[0]
                    # Validate that the extracted main git path exists and is a directory
                    if os.path.isdir(main_git):
                        return main_git
                    else:
                        print(f"Warning: Git worktree detected but main .git directory not found: {main_git}")
                else:
                    print(f"Warning: Git worktree file format unexpected, expected '/worktrees/' in path: {gitdir}")
        except (IOError, OSError) as e:
            print(f"Warning: Failed to read git worktree file {git_path}: {e}")

    return None


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
    """Build the Docker image with all AI CLI tools and Go"""
    if versions is None:
        versions = {"g": "latest", "oac": "latest", "go": "1.24.2"}

    composite_tag = make_composite_tag(versions)
    print(f"Building image with composite tag: {composite_tag}")

    # Build command with all version build args
    build_cmd = [
        "docker", "build",
        "--build-arg", f"GEMINI_CLI_VERSION={versions['g']}",
        "--build-arg", f"OPENAI_CODEX_VERSION={versions['oac']}",
        "--build-arg", f"GO_VERSION={versions['go']}",
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
    """Sync Claude config to container: statusLine section + referenced files + CLAUDE.md + commands dir"""
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

    # Handle commands directory sync (may be a symlink)
    commands_dir = claude_dir / "commands"
    commands_source = None
    if commands_dir.exists():
        # Resolve symlink if it is one
        commands_source = commands_dir.resolve()
        if not commands_source.is_dir():
            commands_source = None

    if commands_source:
        # Remove existing commands directory to ensure clean sync (no stale files)
        subprocess.run(
            ["docker", "exec", container_name, "rm", "-rf", f"{container_claude_dir}/commands"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Create fresh commands directory
        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", f"{container_claude_dir}/commands"],
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
            ["docker", "exec", "-i", container_name, "tar", "-xf", "-", "-C", f"{container_claude_dir}/commands"],
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
            ["docker", "exec", container_name, "rm", "-rf", f"{container_claude_dir}/commands"],
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

    # Auto-detect git worktree and mount main .git directory
    # This allows git operations to work inside the container
    main_git = detect_worktree(cwd)
    if main_git:
        print(f"Detected git worktree, mounting main .git: {main_git}")
        # Mount at same absolute path so .git file references resolve correctly
        docker_cmd.extend(["-v", f"{main_git}:{main_git}"])

    # Add extra mounts from config
    for mount_spec in config.get("mounts", []):
        mount_args = parse_mount(mount_spec, cwd, container_name)
        docker_cmd.extend(mount_args)

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
