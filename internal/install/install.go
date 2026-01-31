package install

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	// ANSI color codes
	reset   = "\033[0m"
	bold    = "\033[1m"
	red     = "\033[91m"
	green   = "\033[92m"
	yellow  = "\033[93m"
	blue    = "\033[94m"
	magenta = "\033[95m"
	cyan    = "\033[96m"
)

// InstallSymlink installs a symlink to ~/.local/bin/vibecon
func InstallSymlink(simulatePathMissing bool) error {
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}

	scriptPath, err := filepath.EvalSymlinks(exePath)
	if err != nil {
		return fmt.Errorf("failed to resolve symlinks: %w", err)
	}

	homeDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("failed to get home directory: %w", err)
	}

	installDir := filepath.Join(homeDir, ".local", "bin")
	symlinkPath := filepath.Join(installDir, "vibecon")

	// Create display version with $HOME substitution
	installDirDisplay := strings.Replace(installDir, homeDir, "$HOME", 1)

	// Create install directory if it doesn't exist
	if err := os.MkdirAll(installDir, 0755); err != nil {
		return fmt.Errorf("failed to create install directory: %w", err)
	}

	// Check if symlink already exists and points to correct target
	alreadyInstalled := false
	if target, err := os.Readlink(symlinkPath); err == nil {
		if resolvedTarget, err := filepath.EvalSymlinks(symlinkPath); err == nil && resolvedTarget == scriptPath {
			alreadyInstalled = true
			fmt.Printf("%s%sAlready installed:%s %s%s%s -> %s%s%s\n",
				green, bold, reset, cyan, symlinkPath, reset, blue, scriptPath, reset)
		}
	}

	if !alreadyInstalled {
		// Remove existing symlink if it exists but points elsewhere
		_ = os.Remove(symlinkPath)

		// Create symlink
		if err := os.Symlink(scriptPath, symlinkPath); err != nil {
			return fmt.Errorf("failed to create symlink: %w", err)
		}
		fmt.Printf("%sInstalled:%s %s%s%s -> %s%s%s\n",
			green, reset, cyan, symlinkPath, reset, blue, scriptPath, reset)
	}

	// Check if install directory is in PATH
	pathEnv := os.Getenv("PATH")
	if simulatePathMissing || !strings.Contains(pathEnv, installDir) {
		printPathWarning(installDirDisplay)
	} else {
		fmt.Printf("\n%s%s✓%s %sYou can now use vibecon by its name:%s %s%svibecon%s\n",
			green, bold, reset, green, reset, cyan, bold, reset)
	}

	return nil
}

// UninstallSymlink removes the symlink from ~/.local/bin/vibecon
func UninstallSymlink() error {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("failed to get home directory: %w", err)
	}

	symlinkPath := filepath.Join(homeDir, ".local", "bin", "vibecon")

	if _, err := os.Lstat(symlinkPath); err == nil {
		if err := os.Remove(symlinkPath); err != nil {
			return fmt.Errorf("failed to remove symlink: %w", err)
		}
		fmt.Printf("Uninstalled: %s\n", symlinkPath)
	} else {
		fmt.Printf("Symlink not found: %s\n", symlinkPath)
	}

	return nil
}

func printPathWarning(installDirDisplay string) {
	// Detect shell
	shellPath := os.Getenv("SHELL")
	shellName := "unknown"
	if shellPath != "" {
		shellName = filepath.Base(shellPath)
	}

	// Determine config file and export syntax
	var configFile, exportCmd string
	switch shellName {
	case "zsh":
		configFile = "~/.zshrc"
		exportCmd = fmt.Sprintf(`export PATH="%s:$PATH"`, installDirDisplay)
	case "bash":
		configFile = "~/.bashrc"
		exportCmd = fmt.Sprintf(`export PATH="%s:$PATH"`, installDirDisplay)
	case "fish":
		configFile = "~/.config/fish/config.fish"
		exportCmd = fmt.Sprintf(`set -gx PATH "%s" $PATH`, installDirDisplay)
	case "tcsh", "csh":
		configFile = "~/.cshrc"
		exportCmd = fmt.Sprintf(`setenv PATH "%s:$PATH"`, installDirDisplay)
	default:
		configFile = "~/.profile"
		exportCmd = fmt.Sprintf(`export PATH="%s:$PATH"`, installDirDisplay)
	}

	// Print warning banner
	fmt.Printf("\n%s%s%s\n", red, bold, strings.Repeat("=", 70))
	fmt.Printf("  ⚠️  WARNING: PATH CUSTOMIZATION REQUIRED\n")
	fmt.Printf("%s%s\n", strings.Repeat("=", 70), reset)
	fmt.Printf("\n  %s%s%s%s %s%s%sis NOT in your PATH!%s\n\n",
		yellow, bold, installDirDisplay, reset, red, bold, reset, reset)
	fmt.Printf("  You must add it to your PATH to use %s%s'vibecon'%s by name.\n",
		cyan, bold, reset)
	fmt.Printf("\n%s%s%s\n", blue, strings.Repeat("─", 70), reset)
	fmt.Printf("  %sDetected shell:%s %s%s%s\n",
		magenta, reset, bold, shellName, reset)
	fmt.Printf("%s%s%s\n", blue, strings.Repeat("─", 70), reset)
	fmt.Printf("\n  Add to PATH %spermanently%s:\n", green, reset)
	fmt.Printf("    %secho '%s' >> %s%s\n", green, exportCmd, configFile, reset)
	fmt.Printf("    %ssource %s%s\n", green, configFile, reset)
	fmt.Printf("\n%s%s%s%s\n\n", red, bold, strings.Repeat("=", 70), reset)
}
