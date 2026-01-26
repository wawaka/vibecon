package sync

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const (
	containerClaudeDir = "/home/node/.claude"
)

// ClaudeSettings represents the subset of Claude settings we sync
type ClaudeSettings struct {
	StatusLine map[string]interface{} `json:"statusLine,omitempty"`
}

// SyncClaudeConfig syncs Claude config to container
func SyncClaudeConfig(containerName string) error {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("failed to get home directory: %w", err)
	}

	claudeDir := filepath.Join(homeDir, ".claude")
	settingsFile := filepath.Join(claudeDir, "settings.json")
	claudeMdFile := filepath.Join(claudeDir, "CLAUDE.md")

	// Track files to copy
	var filesToCopy []string
	containerSettings := ClaudeSettings{}

	// Parse settings.json if it exists
	if _, err := os.Stat(settingsFile); err == nil {
		data, err := os.ReadFile(settingsFile)
		if err == nil {
			var settings map[string]interface{}
			if err := json.Unmarshal(data, &settings); err == nil {
				// Extract statusLine section if present
				if statusLine, ok := settings["statusLine"].(map[string]interface{}); ok {
					containerSettings.StatusLine = statusLine

					// If statusLine has a command, add that file to copy list
					if cmdPath, ok := statusLine["command"].(string); ok {
						// Expand ~ to home directory
						if strings.HasPrefix(cmdPath, "~") {
							cmdPath = filepath.Join(homeDir, cmdPath[1:])
						}
						if _, err := os.Stat(cmdPath); err == nil {
							filesToCopy = append(filesToCopy, cmdPath)
						}
					}
				}
			}
		}
	}

	// Ensure container directory exists
	cmd := exec.Command("docker", "exec", containerName, "mkdir", "-p", containerClaudeDir)
	cmd.Stdout = nil
	cmd.Stderr = nil
	_ = cmd.Run()

	// Handle CLAUDE.md sync
	if _, err := os.Stat(claudeMdFile); err == nil {
		filesToCopy = append(filesToCopy, claudeMdFile)
	} else {
		// Remove from container if doesn't exist locally
		cmd := exec.Command("docker", "exec", containerName, "rm", "-f",
			filepath.Join(containerClaudeDir, "CLAUDE.md"))
		cmd.Stdout = nil
		cmd.Stderr = nil
		_ = cmd.Run()
	}

	// Handle commands directory sync
	commandsDir := filepath.Join(claudeDir, "commands")
	commandsSource := ""
	if info, err := os.Lstat(commandsDir); err == nil {
		if info.Mode()&os.ModeSymlink != 0 {
			// Resolve symlink
			target, err := filepath.EvalSymlinks(commandsDir)
			if err == nil {
				if stat, err := os.Stat(target); err == nil && stat.IsDir() {
					commandsSource = target
				}
			}
		} else if info.IsDir() {
			commandsSource = commandsDir
		}
	}

	if commandsSource != "" {
		// Remove existing commands directory
		cmd := exec.Command("docker", "exec", containerName, "rm", "-rf",
			filepath.Join(containerClaudeDir, "commands"))
		cmd.Stdout = nil
		cmd.Stderr = nil
		_ = cmd.Run()

		// Create fresh commands directory
		cmd = exec.Command("docker", "exec", containerName, "mkdir", "-p",
			filepath.Join(containerClaudeDir, "commands"))
		cmd.Stdout = nil
		cmd.Stderr = nil
		_ = cmd.Run()

		// Copy commands directory using tar
		if err := copyDirToContainer(commandsSource, containerName,
			filepath.Join(containerClaudeDir, "commands")); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: Failed to copy commands directory: %v\n", err)
		}
	} else {
		// Remove commands directory from container
		cmd := exec.Command("docker", "exec", containerName, "rm", "-rf",
			filepath.Join(containerClaudeDir, "commands"))
		cmd.Stdout = nil
		cmd.Stderr = nil
		_ = cmd.Run()
	}

	// Copy files using tar if we have any
	if len(filesToCopy) > 0 {
		if err := copyFilesToContainer(filesToCopy, containerName, containerClaudeDir); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: Failed to copy files: %v\n", err)
		}
	}

	// Write container settings.json if we have settings to write
	if containerSettings.StatusLine != nil {
		settingsJSON, err := json.MarshalIndent(containerSettings, "", "  ")
		if err == nil {
			// Write settings using shell heredoc
			shellCmd := fmt.Sprintf("cat > %s/settings.json << 'EOFCONFIG'\n%s\nEOFCONFIG",
				containerClaudeDir, string(settingsJSON))
			cmd := exec.Command("docker", "exec", containerName, "sh", "-c", shellCmd)
			cmd.Stdout = nil
			_ = cmd.Run()
		}
	}

	// Fix ownership for node user
	cmd = exec.Command("docker", "exec", "-u", "root", containerName,
		"chown", "-R", "node:node", containerClaudeDir)
	cmd.Stdout = nil
	cmd.Stderr = nil
	_ = cmd.Run()

	return nil
}

// copyFilesToContainer copies files to container using tar
func copyFilesToContainer(files []string, containerName, targetDir string) error {
	// Create a temporary directory with just the filenames
	tmpDir, err := os.MkdirTemp("", "vibecon-sync-*")
	if err != nil {
		return fmt.Errorf("failed to create temp dir: %w", err)
	}
	defer os.RemoveAll(tmpDir)

	// Copy files to temp dir with just their basenames
	for _, srcFile := range files {
		data, err := os.ReadFile(srcFile)
		if err != nil {
			continue
		}
		destFile := filepath.Join(tmpDir, filepath.Base(srcFile))
		if err := os.WriteFile(destFile, data, 0644); err != nil {
			continue
		}
		// Preserve executable bit
		if info, err := os.Stat(srcFile); err == nil {
			if info.Mode()&0111 != 0 {
				os.Chmod(destFile, 0755)
			}
		}
	}

	return copyDirToContainer(tmpDir, containerName, targetDir)
}

// copyDirToContainer copies a directory to container using tar
func copyDirToContainer(srcDir, containerName, targetDir string) error {
	// Create tar archive
	tarCmd := exec.Command("tar", "-cf", "-", ".")
	tarCmd.Dir = srcDir
	tarOut, err := tarCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create tar pipe: %w", err)
	}

	// Extract in container
	extractCmd := exec.Command("docker", "exec", "-i", containerName,
		"tar", "-xf", "-", "-C", targetDir)
	extractCmd.Stdin = tarOut

	var extractErr bytes.Buffer
	extractCmd.Stderr = &extractErr

	if err := tarCmd.Start(); err != nil {
		return fmt.Errorf("failed to start tar: %w", err)
	}

	if err := extractCmd.Run(); err != nil {
		return fmt.Errorf("failed to extract tar: %s", extractErr.String())
	}

	if err := tarCmd.Wait(); err != nil {
		return fmt.Errorf("tar command failed: %w", err)
	}

	return nil
}
