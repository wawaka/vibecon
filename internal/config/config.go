package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Config represents the vibecon configuration
type Config struct {
	Mounts []Mount `json:"mounts"`
}

// Mount represents a mount specification
type Mount struct {
	Type     string `json:"type"`                // "bind", "volume", or "anonymous"
	Source   string `json:"source,omitempty"`    // Required for bind and volume
	Target   string `json:"target"`              // Required for all
	ReadOnly bool   `json:"read_only,omitempty"` // Optional
	UID      *int   `json:"uid,omitempty"`       // Optional, for volumes only
	GID      *int   `json:"gid,omitempty"`       // Optional, for volumes only
	SELinux  string `json:"selinux,omitempty"`   // Optional: "z" or "Z"
	Global   bool   `json:"global,omitempty"`    // Optional, for volumes only
}

// LoadConfig loads a JSON config file from the given path
func LoadConfig(configPath string) (*Config, error) {
	path := expandPath(configPath)

	// Return empty config if file doesn't exist
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return &Config{Mounts: []Mount{}}, nil
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file %s: %w", path, err)
	}

	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("invalid JSON in %s: %w", path, err)
	}

	return &cfg, nil
}

// GetMergedConfig loads and merges global and project configs
func GetMergedConfig(projectRoot string) (*Config, error) {
	// Load global config
	globalCfg, err := LoadConfig("~/.vibecon.json")
	if err != nil {
		return nil, err
	}

	// Load project config
	projectConfigPath := filepath.Join(projectRoot, ".vibecon.json")
	projectCfg, err := LoadConfig(projectConfigPath)
	if err != nil {
		return nil, err
	}

	// Merge: global mounts first, then project mounts
	merged := &Config{
		Mounts: append(globalCfg.Mounts, projectCfg.Mounts...),
	}

	return merged, nil
}

// expandPath expands ~ to home directory
func expandPath(path string) string {
	if len(path) > 0 && path[0] == '~' {
		home, err := os.UserHomeDir()
		if err != nil {
			return path
		}
		return filepath.Join(home, path[1:])
	}
	return path
}
