package version

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"strings"
	"sync"
)

// GetAllVersions fetches versions of all tools concurrently
func GetAllVersions() (map[string]string, error) {
	fmt.Println("Checking latest versions...")

	versions := make(map[string]string)
	var mu sync.Mutex
	var wg sync.WaitGroup
	errChan := make(chan error, 3)

	// Fetch Gemini CLI version
	wg.Add(1)
	go func() {
		defer wg.Done()
		version, err := getNpmPackageVersion("@google/gemini-cli")
		mu.Lock()
		defer mu.Unlock()
		if err != nil {
			versions["g"] = "latest"
			fmt.Printf("  Gemini CLI: latest (failed to fetch)\n")
		} else {
			versions["g"] = version
			fmt.Printf("  Gemini CLI: %s\n", version)
		}
	}()

	// Fetch OpenAI Codex version
	wg.Add(1)
	go func() {
		defer wg.Done()
		version, err := getNpmPackageVersion("@openai/codex")
		mu.Lock()
		defer mu.Unlock()
		if err != nil {
			versions["oac"] = "latest"
			fmt.Printf("  OpenAI Codex: latest (failed to fetch)\n")
		} else {
			versions["oac"] = version
			fmt.Printf("  OpenAI Codex: %s\n", version)
		}
	}()

	// Fetch Go version
	wg.Add(1)
	go func() {
		defer wg.Done()
		version, err := getGoVersion()
		mu.Lock()
		defer mu.Unlock()
		if err != nil {
			versions["go"] = "1.24.2"
			fmt.Printf("  Go: 1.24.2 (failed to fetch, using fallback)\n")
		} else {
			versions["go"] = version
			fmt.Printf("  Go: %s\n", version)
		}
	}()

	wg.Wait()
	close(errChan)

	return versions, nil
}

// getNpmPackageVersion fetches the latest version of an npm package
func getNpmPackageVersion(packageName string) (string, error) {
	cmd := exec.Command("npm", "view", packageName, "version")
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("failed to get npm package version: %w", err)
	}
	return strings.TrimSpace(string(output)), nil
}

// getGoVersion fetches the latest stable Go version from golang.org
func getGoVersion() (string, error) {
	resp, err := http.Get("https://go.dev/dl/?mode=json")
	if err != nil {
		return "", fmt.Errorf("failed to fetch Go version: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read response: %w", err)
	}

	var releases []struct {
		Version string `json:"version"`
		Stable  bool   `json:"stable"`
	}

	if err := json.Unmarshal(body, &releases); err != nil {
		return "", fmt.Errorf("failed to parse JSON: %w", err)
	}

	// Find first stable release
	for _, release := range releases {
		if release.Stable {
			// Version is like "go1.24.2", strip the "go" prefix
			return strings.TrimPrefix(release.Version, "go"), nil
		}
	}

	return "", fmt.Errorf("no stable Go version found")
}

// MakeCompositeTag creates a composite tag from versions
func MakeCompositeTag(versions map[string]string) string {
	return fmt.Sprintf("g%s_oac%s_go%s", versions["g"], versions["oac"], versions["go"])
}
