#!/usr/bin/env python3

import subprocess
import os
import sys
import hashlib
import argparse
from pathlib import Path

# Global configuration
IMAGE_NAME = "vibecon:latest"
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

    # Create install directory if it doesn't exist
    install_dir.mkdir(parents=True, exist_ok=True)

    # Check if symlink already exists and points to the correct target
    already_installed = False
    if symlink_path.is_symlink() and symlink_path.resolve() == script_path:
        already_installed = True
        print(f"{GREEN}{BOLD}Already installed{RESET}")
    else:
        # Remove existing symlink if it exists but points elsewhere
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()

        # Create symlink
        symlink_path.symlink_to(script_path)
        print(f"{GREEN}Installed:{RESET} {CYAN}{symlink_path}{RESET} -> {BLUE}{script_path}{RESET}")

    # Check if install directory is in PATH
    path_env = os.environ.get("PATH", "")
    install_dir_str = str(install_dir)
    if simulate_path_missing or install_dir_str not in path_env.split(os.pathsep):
        # Detect user's shell
        shell_path = os.environ.get("SHELL", "")
        shell_name = os.path.basename(shell_path) if shell_path else "unknown"

        # Determine config file and export syntax based on shell
        if shell_name == "zsh":
            config_file = "~/.zshrc"
            export_cmd = f'export PATH="{install_dir}:$PATH"'
        elif shell_name == "bash":
            config_file = "~/.bashrc"
            export_cmd = f'export PATH="{install_dir}:$PATH"'
        elif shell_name == "fish":
            config_file = "~/.config/fish/config.fish"
            export_cmd = f'set -gx PATH "{install_dir}" $PATH'
        elif shell_name in ["tcsh", "csh"]:
            config_file = "~/.cshrc"
            export_cmd = f'setenv PATH "{install_dir}:$PATH"'
        else:
            config_file = "~/.profile"
            export_cmd = f'export PATH="{install_dir}:$PATH"'

        # Print large banner warning with colors
        print(f"\n{RED}{BOLD}{'=' * 70}")
        print(f"  ⚠️  WARNING: PATH CUSTOMIZATION REQUIRED")
        print(f"{'=' * 70}{RESET}")
        print(f"\n  {YELLOW}{BOLD}{install_dir}{RESET} {RED}{BOLD}is NOT in your PATH!{RESET}\n")
        print(f"  You must add it to your PATH to use {CYAN}{BOLD}'vibecon'{RESET} by name.")
        print(f"\n{BLUE}{'─' * 70}{RESET}")
        print(f"  {MAGENTA}Detected shell:{RESET} {BOLD}{shell_name}{RESET}")
        print(f"{BLUE}{'─' * 70}{RESET}")
        print(f"\n  {BOLD}Option 1:{RESET} Add to PATH for {YELLOW}CURRENT shell only{RESET} (temporary):")
        print(f"    {GREEN}{export_cmd}{RESET}")
        print(f"\n  {BOLD}Option 2:{RESET} Add to PATH {GREEN}PERMANENTLY{RESET} (recommended):")
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

def kill_container(container_name):
    """Kill and remove the container"""
    print(f"Killing container '{container_name}'...")
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Container killed.")

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
    # Create a short hash from the workspace path
    path_hash = hashlib.md5(workspace_path.encode()).hexdigest()[:8]

    # Sanitize the path for use in container name
    # Remove leading slash and replace special chars with hyphens
    sanitized_path = workspace_path.lstrip('/').replace('/', '-').replace('_', '-').lower()

    # Limit length to avoid overly long names
    if len(sanitized_path) > 40:
        sanitized_path = sanitized_path[:40]

    return f"vibecon-{sanitized_path}-{path_hash}"

def image_exists(image_name):
    """Check if Docker image exists"""
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0

def get_latest_claude_version():
    """Get the latest version of @anthropic-ai/claude-code from npm"""
    print("Checking latest claude-code version from npm...")
    result = subprocess.run(
        ["npm", "view", "@anthropic-ai/claude-code", "version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode == 0:
        version = result.stdout.strip()
        print(f"Latest claude-code version: {version}")
        return version
    else:
        print("Warning: Failed to get latest version from npm, using 'latest'")
        return "latest"

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

def build_image(vibecon_root, image_name, claude_version=None):
    """Build the Docker image"""
    if claude_version is None:
        claude_version = "latest"

    print(f"Building image '{image_name}' with claude-code@{claude_version}...")

    # Build command with version tag
    build_cmd = [
        "docker", "build",
        "--build-arg", f"CLAUDE_CODE_VERSION={claude_version}",
        "-t", image_name
    ]

    # Add version-specific tag if not "latest"
    if claude_version != "latest":
        version_tag = f"vibecon:{claude_version}"
        build_cmd.extend(["-t", version_tag])
        print(f"Tagging as: {image_name} and {version_tag}")

    build_cmd.append(".")

    build_result = subprocess.run(build_cmd, cwd=vibecon_root)
    if build_result.returncode != 0:
        print("Failed to build image")
        sys.exit(1)

def start_container(cwd, container_name, image_name):
    """Start the container in detached mode"""
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

    # Add volume mount and image
    docker_cmd.extend([
        "-v", f"{cwd}:/workspace",
        image_name
    ])

    # Start container detached with sleep infinity to keep it running
    run_result = subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if run_result.returncode != 0:
        print(f"Failed to start container: {run_result.stderr.decode()}")
        sys.exit(1)

def ensure_container_running(cwd, vibecon_root, container_name, image_name):
    """Ensure container is running"""
    if not is_container_running(container_name):
        # Remove stopped container if it exists
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Build image only if it doesn't exist
        if not image_exists(image_name):
            print(f"Image '{image_name}' not found, building...")
            build_image(vibecon_root, image_name)
        start_container(cwd, container_name, image_name)

def main():
    parser = argparse.ArgumentParser(
        description="vibecon - Persistent Docker container environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s                    # Start "{' '.join(DEFAULT_COMMAND)}" in container
  %(prog)s zsh                # Run zsh in container
  %(prog)s claude             # Run claude in container
  %(prog)s ls -la             # Run 'ls -la' in container
  %(prog)s -b                 # Rebuild image and start zsh
  %(prog)s -k                 # Kill container for current workspace
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
        "-k", "--kill",
        action="store_true",
        help="kill and remove the container for current workspace"
    )

    parser.add_argument(
        "-b", "--build",
        action="store_true",
        help="force rebuild the Docker image"
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

    # Handle build flag - get latest version and build the image
    if args.build:
        claude_version = get_latest_claude_version()
        build_image(vibecon_root, IMAGE_NAME, claude_version)
        sys.exit(0)

    # Handle kill flag - just kill the container and exit
    if args.kill:
        kill_container(container_name)
        sys.exit(0)

    # Get command to execute (use default if not specified)
    command = args.command if args.command else DEFAULT_COMMAND

    # Ensure container is running
    ensure_container_running(cwd, vibecon_root, container_name, IMAGE_NAME)

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
