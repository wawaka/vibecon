package docker

import (
	"bytes"
	"crypto/md5"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/wawaka/vibecon/internal/config"
	"github.com/wawaka/vibecon/internal/mount"
	"github.com/wawaka/vibecon/internal/version"
)

// GenerateContainerName creates a container name based on workspace path
func GenerateContainerName(workspacePath string) string {
	// Create hash from workspace path
	hash := md5.Sum([]byte(workspacePath))
	pathHash := fmt.Sprintf("%x", hash)[:8]

	// Sanitize path for container name
	sanitized := strings.TrimPrefix(workspacePath, "/")
	sanitized = strings.ReplaceAll(sanitized, "/", "-")
	sanitized = strings.ReplaceAll(sanitized, "_", "-")
	sanitized = strings.ToLower(sanitized)

	return fmt.Sprintf("vibecon-%s-%s", sanitized, pathHash)
}

// IsContainerRunning checks if a container is running
func IsContainerRunning(containerName string) (bool, error) {
	cmd := exec.Command("docker", "inspect", "-f", "{{.State.Running}}", containerName)
	output, err := cmd.Output()
	if err != nil {
		return false, nil // Container doesn't exist or error
	}
	return strings.TrimSpace(string(output)) == "true", nil
}

// ContainerExists checks if a container exists (in any state)
func ContainerExists(containerName string) bool {
	cmd := exec.Command("docker", "inspect", containerName)
	cmd.Stdout = nil
	cmd.Stderr = nil
	return cmd.Run() == nil
}

// RestartContainer attempts to restart a stopped container
func RestartContainer(containerName string) error {
	fmt.Printf("Found stopped container '%s', attempting to restart...\n", containerName)
	cmd := exec.Command("docker", "start", containerName)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to restart container: %w", err)
	}
	fmt.Printf("Container '%s' restarted successfully.\n", containerName)
	return nil
}

// StopContainer stops a running container
func StopContainer(containerName string) error {
	fmt.Printf("Stopping container '%s'...\n", containerName)
	cmd := exec.Command("docker", "stop", containerName)
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Run(); err != nil {
		fmt.Println("Container was not running.")
		return nil
	}
	fmt.Println("Container stopped.")
	return nil
}

// DestroyContainer permanently removes a container
func DestroyContainer(containerName string) error {
	fmt.Printf("Destroying container '%s'...\n", containerName)
	cmd := exec.Command("docker", "rm", "-f", containerName)
	cmd.Stdout = nil
	cmd.Stderr = nil
	_ = cmd.Run()
	fmt.Println("Container destroyed.")
	return nil
}

// ImageExists checks if a Docker image exists
func ImageExists(imageName string) (bool, error) {
	cmd := exec.Command("docker", "image", "inspect", imageName)
	var stderr bytes.Buffer
	cmd.Stdout = nil
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		stderrStr := stderr.String()
		if strings.Contains(strings.ToLower(stderrStr), "no such image") {
			return false, nil
		}
		return false, fmt.Errorf("error checking image: %s", stderrStr)
	}
	return true, nil
}

// BuildImage builds the Docker image with version tags
func BuildImage(vibeconRoot, imageName string, versions map[string]string) error {
	compositeTag := version.MakeCompositeTag(versions)
	fmt.Printf("Building image with composite tag: %s\n", compositeTag)

	args := []string{
		"build",
		"--build-arg", fmt.Sprintf("GEMINI_CLI_VERSION=%s", versions["g"]),
		"--build-arg", fmt.Sprintf("OPENAI_CODEX_VERSION=%s", versions["oac"]),
		"--build-arg", fmt.Sprintf("GO_VERSION=%s", versions["go"]),
		"-t", imageName,
		"-t", fmt.Sprintf("vibecon:%s", compositeTag),
		".",
	}

	fmt.Printf("Tagging as: %s and vibecon:%s\n", imageName, compositeTag)

	cmd := exec.Command("docker", args...)
	cmd.Dir = vibeconRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to build image: %w", err)
	}

	return nil
}

// GetGitUserInfo retrieves git user.name and user.email from host
func GetGitUserInfo() (string, string) {
	var userName, userEmail string

	// Get git user.name
	cmd := exec.Command("git", "config", "--global", "user.name")
	if output, err := cmd.Output(); err == nil {
		userName = strings.TrimSpace(string(output))
	}

	// Get git user.email
	cmd = exec.Command("git", "config", "--global", "user.email")
	if output, err := cmd.Output(); err == nil {
		userEmail = strings.TrimSpace(string(output))
	}

	return userName, userEmail
}

// GetHostTimezone retrieves the host system timezone
func GetHostTimezone() string {
	// Try TZ environment variable
	if tz := os.Getenv("TZ"); tz != "" {
		return tz
	}

	// Try /etc/timezone (Debian/Ubuntu)
	if data, err := os.ReadFile("/etc/timezone"); err == nil {
		if tz := strings.TrimSpace(string(data)); tz != "" {
			return tz
		}
	}

	// Try timedatectl (systemd)
	cmd := exec.Command("timedatectl", "show", "-p", "Timezone", "--value")
	if output, err := cmd.Output(); err == nil {
		if tz := strings.TrimSpace(string(output)); tz != "" {
			return tz
		}
	}

	// Try /etc/localtime symlink
	if target, err := filepath.EvalSymlinks("/etc/localtime"); err == nil {
		parts := strings.Split(target, "/")
		for i, part := range parts {
			if part == "zoneinfo" && i+1 < len(parts) {
				return strings.Join(parts[i+1:], "/")
			}
		}
	}

	return "UTC"
}

// StartContainer starts a new container in detached mode
func StartContainer(cwd, containerName, imageName string, cfg *config.Config) error {
	hostTerm := os.Getenv("TERM")
	if hostTerm == "" {
		hostTerm = "xterm-256color"
	}
	containerHostname := "vibecon"

	// Get git user info
	gitUserName, gitUserEmail := GetGitUserInfo()
	if gitUserName != "" {
		fmt.Printf("Configuring git user: %s <%s>\n", gitUserName, gitUserEmail)
	}

	// Get host timezone
	hostTimezone := GetHostTimezone()
	fmt.Printf("Configuring timezone: %s\n", hostTimezone)

	fmt.Printf("Starting container '%s' with %s mounted at /workspace...\n", containerName, cwd)

	// Build docker run command
	args := []string{
		"run",
		"-d",
		"--name", containerName,
		"--hostname", containerHostname,
		"-e", fmt.Sprintf("TERM=%s", hostTerm),
		"-e", "COLORTERM=truecolor",
		"-e", fmt.Sprintf("TZ=%s", hostTimezone),
	}

	// Add git user environment variables if available
	if gitUserName != "" {
		args = append(args,
			"-e", fmt.Sprintf("GIT_USER_NAME=%s", gitUserName),
			"-e", fmt.Sprintf("GIT_USER_EMAIL=%s", gitUserEmail),
		)
	}

	// Add main workspace volume mount
	args = append(args, "-v", fmt.Sprintf("%s:/workspace", cwd))

	// Add extra mounts from config
	for _, m := range cfg.Mounts {
		mountArgs, err := mount.ParseMount(m, cwd, containerName)
		if err != nil {
			return fmt.Errorf("failed to parse mount: %w", err)
		}
		args = append(args, mountArgs...)
	}

	// Add image name and command
	args = append(args, imageName)

	cmd := exec.Command("docker", args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to start container: %s", stderr.String())
	}

	return nil
}

// EnsureContainerRunning ensures the container is running
func EnsureContainerRunning(cwd, vibeconRoot, containerName, imageName string, cfg *config.Config) error {
	running, err := IsContainerRunning(containerName)
	if err != nil {
		return err
	}
	if running {
		return nil // Already running
	}

	// Container not running - check if it exists (stopped/dead)
	if ContainerExists(containerName) {
		// Try to restart
		if err := RestartContainer(containerName); err == nil {
			return nil // Successfully restarted
		}
		// Restart failed, remove and recreate
		fmt.Println("Restart failed, removing container and creating a new one...")
		_ = DestroyContainer(containerName)
	}

	// Build image only if it doesn't exist
	exists, err := ImageExists(imageName)
	if err != nil {
		return err
	}
	if !exists {
		fmt.Printf("Image '%s' not found, building...\n", imageName)
		versions := map[string]string{"g": "latest", "oac": "latest", "go": "1.24.2"}
		if err := BuildImage(vibeconRoot, imageName, versions); err != nil {
			return err
		}
	}

	return StartContainer(cwd, containerName, imageName, cfg)
}

// ExecInContainer executes a command in the container
func ExecInContainer(containerName string, command []string) (int, error) {
	hostTerm := os.Getenv("TERM")
	if hostTerm == "" {
		hostTerm = "xterm-256color"
	}
	hostTimezone := GetHostTimezone()

	args := []string{
		"exec",
		"-it",
		"-e", fmt.Sprintf("TERM=%s", hostTerm),
		"-e", "COLORTERM=truecolor",
		"-e", fmt.Sprintf("TZ=%s", hostTimezone),
		containerName,
	}
	args = append(args, command...)

	cmd := exec.Command("docker", args...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return exitErr.ExitCode(), nil
		}
		return 1, err
	}

	return 0, nil
}
