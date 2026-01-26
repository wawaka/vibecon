package mount

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/wawaka/vibecon/internal/config"
)

// ParseMount converts a mount specification into Docker arguments
// Returns a slice of arguments like ["-v", "..."] or ["--mount", "..."]
func ParseMount(mount config.Mount, projectRoot, containerName string) ([]string, error) {
	if mount.Target == "" {
		return nil, fmt.Errorf("mount missing required 'target' field")
	}

	switch mount.Type {
	case "anonymous":
		return parseAnonymousMount(mount)
	case "bind":
		return parseBindMount(mount, projectRoot)
	case "volume":
		return parseVolumeMount(mount, containerName)
	default:
		return nil, fmt.Errorf("unknown mount type '%s'. Must be 'bind', 'volume', or 'anonymous'", mount.Type)
	}
}

func parseAnonymousMount(mount config.Mount) ([]string, error) {
	if mount.UID != nil || mount.GID != nil {
		// Use --mount syntax with tmpfs backing for uid/gid support
		mountOpts := []string{}
		if mount.UID != nil {
			mountOpts = append(mountOpts, fmt.Sprintf("uid=%d", *mount.UID))
		}
		if mount.GID != nil {
			mountOpts = append(mountOpts, fmt.Sprintf("gid=%d", *mount.GID))
		}
		driverOpts := fmt.Sprintf("o=%s", strings.Join(mountOpts, ","))

		parts := []string{
			"type=volume",
			fmt.Sprintf("target=%s", mount.Target),
			"volume-opt=type=tmpfs",
			"volume-opt=device=tmpfs",
			fmt.Sprintf(`"volume-opt=%s"`, driverOpts),
		}
		if mount.ReadOnly {
			parts = append(parts, "readonly")
		}
		return []string{"--mount", strings.Join(parts, ",")}, nil
	}

	return []string{"-v", mount.Target}, nil
}

func parseBindMount(mount config.Mount, projectRoot string) ([]string, error) {
	if mount.Source == "" {
		return nil, fmt.Errorf("bind mount missing required 'source' field")
	}

	// Warn if uid/gid specified (not supported for bind mounts)
	if mount.UID != nil || mount.GID != nil {
		fmt.Fprintf(os.Stderr, "Warning: uid/gid options ignored for bind mount (not supported by Docker)\n")
	}

	// Resolve source path
	resolved := expandPath(mount.Source)
	if !filepath.IsAbs(resolved) {
		resolved = filepath.Join(projectRoot, resolved)
		resolved = filepath.Clean(resolved)
	}

	// Warn if source doesn't exist
	if _, err := os.Stat(resolved); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "Warning: bind mount source does not exist: %s\n", resolved)
	}

	// Build mount argument
	mountArg := fmt.Sprintf("%s:%s", resolved, mount.Target)
	suffixOpts := []string{}
	if mount.ReadOnly {
		suffixOpts = append(suffixOpts, "ro")
	}
	if mount.SELinux != "" {
		suffixOpts = append(suffixOpts, mount.SELinux)
	}
	if len(suffixOpts) > 0 {
		mountArg += ":" + strings.Join(suffixOpts, ",")
	}

	return []string{"-v", mountArg}, nil
}

func parseVolumeMount(mount config.Mount, containerName string) ([]string, error) {
	if mount.Source == "" {
		return nil, fmt.Errorf("volume mount missing required 'source' field")
	}

	// Determine volume name based on global flag
	volumeName := mount.Source
	if !mount.Global {
		volumeName = fmt.Sprintf("%s_%s", containerName, mount.Source)
	}

	// If uid/gid specified, use --mount syntax with tmpfs backing
	if mount.UID != nil || mount.GID != nil {
		mountOpts := []string{}
		if mount.UID != nil {
			mountOpts = append(mountOpts, fmt.Sprintf("uid=%d", *mount.UID))
		}
		if mount.GID != nil {
			mountOpts = append(mountOpts, fmt.Sprintf("gid=%d", *mount.GID))
		}
		driverOpts := fmt.Sprintf("o=%s", strings.Join(mountOpts, ","))

		parts := []string{
			"type=volume",
			fmt.Sprintf("source=%s", volumeName),
			fmt.Sprintf("target=%s", mount.Target),
			"volume-opt=type=tmpfs",
			"volume-opt=device=tmpfs",
			fmt.Sprintf(`"volume-opt=%s"`, driverOpts),
		}
		if mount.ReadOnly {
			parts = append(parts, "readonly")
		}
		return []string{"--mount", strings.Join(parts, ",")}, nil
	}

	// Simple -v syntax
	mountArg := fmt.Sprintf("%s:%s", volumeName, mount.Target)
	suffixOpts := []string{}
	if mount.ReadOnly {
		suffixOpts = append(suffixOpts, "ro")
	}
	if mount.SELinux != "" {
		suffixOpts = append(suffixOpts, mount.SELinux)
	}
	if len(suffixOpts) > 0 {
		mountArg += ":" + strings.Join(suffixOpts, ",")
	}

	return []string{"-v", mountArg}, nil
}

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
