"""Installation and symlink management for Vibecon."""

import os
import subprocess
import sys
from pathlib import Path


class InstallationManager:
    """Manages symlink installation and uninstallation for Vibecon."""
    
    def __init__(self):
        # We need to find the original vibecon.py script, not this package
        # The script should be in the parent directory of the vibecon package
        self.script_path = Path(__file__).resolve().parent.parent / "vibecon.py"
    
    def install_symlink(self, simulate_path_missing: bool = False) -> None:
        """Install symlink to ~/.local/bin/vibecon."""
        # ANSI color codes
        RESET = "\033[0m"
        BOLD = "\033[1m"
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        MAGENTA = "\033[95m"
        CYAN = "\033[96m"

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
        if symlink_path.is_symlink() and symlink_path.resolve() == self.script_path:
            already_installed = True
            print(f"{GREEN}{BOLD}Already installed:{RESET} {CYAN}{symlink_path}{RESET} -> {BLUE}{self.script_path}{RESET}")
        else:
            # Remove existing symlink if it exists but points elsewhere
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()

            # Create symlink
            symlink_path.symlink_to(self.script_path)
            print(f"{GREEN}Installed:{RESET} {CYAN}{symlink_path}{RESET} -> {BLUE}{self.script_path}{RESET}")

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

    def uninstall_symlink(self) -> None:
        """Uninstall symlink from ~/.local/bin/vibecon."""
        symlink_path = Path.home() / ".local" / "bin" / "vibecon"

        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
            print(f"Uninstalled: {symlink_path}")
        else:
            print(f"Symlink not found: {symlink_path}")