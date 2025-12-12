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

def install_symlink():
    """Install symlink to ~/.local/bin/vibecon"""
    script_path = Path(__file__).resolve()
    install_dir = Path.home() / ".local" / "bin"
    symlink_path = install_dir / "vibecon"

    # Create install directory if it doesn't exist
    install_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing symlink if it exists
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()

    # Create symlink
    symlink_path.symlink_to(script_path)
    print(f"Installed: {symlink_path} -> {script_path}")

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

    print(f"Starting container '{container_name}' with {cwd} mounted at /workspace...")

    # Build docker run command
    docker_cmd = [
        "docker", "run",
        "-d",
        "--name", container_name,
        "--hostname", container_hostname,
        "-e", f"TERM={host_term}",
        "-e", "COLORTERM=truecolor",
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

    exec_result = subprocess.run(
        [
            "docker", "exec",
            "-it",
            "-e", f"TERM={host_term}",
            "-e", "COLORTERM=truecolor",
            container_name
        ] + command
    )

    sys.exit(exec_result.returncode)

if __name__ == "__main__":
    main()
