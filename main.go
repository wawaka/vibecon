package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/wawaka/vibecon/internal/config"
	"github.com/wawaka/vibecon/internal/docker"
	"github.com/wawaka/vibecon/internal/install"
	"github.com/wawaka/vibecon/internal/sync"
	"github.com/wawaka/vibecon/internal/version"
)

const (
	ImageName      = "vibecon:latest"
	DefaultCommand = "claude"
)

var (
	installFlag      bool
	installTestFlag  bool
	uninstallFlag    bool
	stopFlag         bool
	destroyFlag      bool
	buildFlag        bool
	forceBuildFlag   bool
)

func init() {
	flag.BoolVar(&installFlag, "i", false, "install symlink to ~/.local/bin/vibecon")
	flag.BoolVar(&installFlag, "install", false, "install symlink to ~/.local/bin/vibecon")
	flag.BoolVar(&installTestFlag, "I", false, "")
	flag.BoolVar(&uninstallFlag, "u", false, "uninstall symlink from ~/.local/bin/vibecon")
	flag.BoolVar(&uninstallFlag, "uninstall", false, "uninstall symlink from ~/.local/bin/vibecon")
	flag.BoolVar(&stopFlag, "k", false, "stop the container for current workspace")
	flag.BoolVar(&stopFlag, "stop", false, "stop the container for current workspace")
	flag.BoolVar(&destroyFlag, "K", false, "destroy and remove the container permanently")
	flag.BoolVar(&destroyFlag, "destroy", false, "destroy and remove the container permanently")
	flag.BoolVar(&buildFlag, "b", false, "rebuild the Docker image (skips if versions unchanged)")
	flag.BoolVar(&buildFlag, "build", false, "rebuild the Docker image (skips if versions unchanged)")
	flag.BoolVar(&forceBuildFlag, "B", false, "force rebuild even if image exists")
	flag.BoolVar(&forceBuildFlag, "force-build", false, "force rebuild even if image exists")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options] [command...]\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "vibecon - Persistent Docker container environment\n\n")
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExamples:\n")
		fmt.Fprintf(os.Stderr, "  %s                    # Start claude in container\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s zsh                # Run zsh in container\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s claude             # Run Claude Code in container\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s gemini             # Run Gemini CLI in container\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s codex              # Run OpenAI Codex in container\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -b                 # Check versions and rebuild if updated\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -B                 # Force rebuild regardless of versions\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -k                 # Stop container (can be restarted)\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -K                 # Destroy container permanently\n", os.Args[0])
	}
}

func main() {
	flag.Parse()

	// Handle install flag
	if installFlag {
		if err := install.InstallSymlink(false); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		os.Exit(0)
	}

	// Handle install test flag (hidden)
	if installTestFlag {
		if err := install.InstallSymlink(true); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		os.Exit(0)
	}

	// Handle uninstall flag
	if uninstallFlag {
		if err := install.UninstallSymlink(); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		os.Exit(0)
	}

	// Get current working directory
	cwd, err := os.Getwd()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: Failed to get current directory: %v\n", err)
		os.Exit(1)
	}

	// Find vibecon root (where Dockerfile is)
	vibeconRoot, err := findVibeconRoot()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Generate container name based on workspace path
	containerName := docker.GenerateContainerName(cwd)

	// Load and merge config files
	cfg, err := config.GetMergedConfig(cwd)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Handle build flags
	if buildFlag || forceBuildFlag {
		versions, err := version.GetAllVersions()
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}

		compositeTag := version.MakeCompositeTag(versions)
		versionedImage := fmt.Sprintf("vibecon:%s", compositeTag)

		exists, err := docker.ImageExists(versionedImage)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}

		if exists && !forceBuildFlag {
			fmt.Printf("\nImage already exists: %s\n", versionedImage)
			fmt.Println("No rebuild needed - all versions are up to date.")
			fmt.Println("Use -B/--force-build to rebuild anyway.")
		} else {
			if forceBuildFlag && exists {
				fmt.Println("\nForce rebuild requested...")
			} else {
				fmt.Println("\nNew versions detected, building image...")
			}

			if err := docker.BuildImage(vibeconRoot, ImageName, versions); err != nil {
				fmt.Fprintf(os.Stderr, "Error: %v\n", err)
				os.Exit(1)
			}

			fmt.Printf("\nBuild complete! Image tagged as:\n")
			fmt.Printf("  - %s\n", ImageName)
			fmt.Printf("  - %s\n", versionedImage)
		}
		os.Exit(0)
	}

	// Handle stop flag
	if stopFlag {
		if err := docker.StopContainer(containerName); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		os.Exit(0)
	}

	// Handle destroy flag
	if destroyFlag {
		if err := docker.DestroyContainer(containerName); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		os.Exit(0)
	}

	// Get command to execute
	command := flag.Args()
	if len(command) == 0 {
		command = []string{DefaultCommand, "--dangerously-skip-permissions"}
	}

	// Ensure container is running
	if err := docker.EnsureContainerRunning(cwd, vibeconRoot, containerName, ImageName, cfg); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Sync claude config before exec
	if err := sync.SyncClaudeConfig(containerName); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to sync Claude config: %v\n", err)
	}

	// Execute command in container
	exitCode, err := docker.ExecInContainer(containerName, command)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	os.Exit(exitCode)
}

func findVibeconRoot() (string, error) {
	// Get the executable path
	exePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("failed to get executable path: %w", err)
	}

	// Resolve symlinks
	realPath, err := filepath.EvalSymlinks(exePath)
	if err != nil {
		return "", fmt.Errorf("failed to resolve symlinks: %w", err)
	}

	// Get directory containing the executable
	exeDir := filepath.Dir(realPath)

	// Check if Dockerfile exists in that directory
	dockerfilePath := filepath.Join(exeDir, "Dockerfile")
	if _, err := os.Stat(dockerfilePath); err == nil {
		return exeDir, nil
	}

	return "", fmt.Errorf("could not find Dockerfile in vibecon directory")
}
