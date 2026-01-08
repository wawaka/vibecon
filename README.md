# vibecon

Persistent Docker containers for Claude Code, Gemini CLI, and OpenAI Codex.

## Quick Start

```bash
# Install
./vibecon.py -i
export PATH="$HOME/.local/bin:$PATH"  # add to shell rc

# Run Claude Code in any project
cd /path/to/your/project
vibecon
```

First run builds the image and creates a container. Subsequent runs reuse the same container.

## Usage

```bash
vibecon                  # Run Claude Code (default)
vibecon zsh              # Run shell in container
vibecon gemini           # Run Gemini CLI
vibecon codex            # Run OpenAI Codex
vibecon <any command>    # Run any command
```

## Container Management

```bash
vibecon -k               # Stop container (restarts on next vibecon)
vibecon -K               # Destroy container permanently
vibecon -b               # Rebuild image if new versions available
vibecon -B               # Force rebuild
```

## How It Works

- Each workspace directory gets its own persistent container
- Your project is mounted at `/workspace`
- Container state (history, config) persists across sessions
- Container naming: `vibecon-{path}-{hash}`

## Container Environment

- Base: node:24 with zsh, git, fzf, gh, delta, nano, vim
- AI tools: claude-code, gemini-cli, codex (latest from npm)
- Runs as non-root `node` user
- Git config inherited from host

## Configuration

Optional config files: `~/.vibecon.json` (global) and `./.vibecon.json` (project)

```json
{
  "volumes": {
    "node_modules": {},
    "npm_cache": { "global": true }
  },
  "mounts": [
    "node_modules:/workspace/node_modules",
    "npm_cache:/home/node/.npm",
    "./data:/data:ro",
    "/workspace/.cache"
  ]
}
```

### Mount Types

| Type | Syntax | Description |
|------|--------|-------------|
| Bind mount | `./src:/dst` | Host path (relative or absolute) |
| Named volume | `vol:/dst` | Local to project container |
| Global volume | `vol:/dst` + `{"global": true}` | Shared across projects |
| Anonymous volume | `/container/path` | Ephemeral, not persisted |

### Mount Options

Options can be appended after the target path with a colon:

```
source:target:options
```

| Option | Description |
|--------|-------------|
| `ro` | Read-only mount |
| `z` | SELinux shared label |
| `Z` | SELinux private label |
| `uid=N` | Set owner UID (volumes only) |
| `gid=N` | Set owner GID (volumes only) |

Examples:
```json
{
  "volumes": {
    "mydata": {},
    "shared_cache": { "global": true }
  },
  "mounts": [
    "./config:/app/config:ro",
    "./logs:/app/logs:z",
    "mydata:/data:uid=1000,gid=1000",
    "shared_cache:/cache:ro,uid=1000,gid=1000"
  ]
}
```

### Long Syntax

For more control, use object syntax:
```json
{
  "mounts": [
    {
      "source": "myvolume",
      "target": "/app/data",
      "uid": 1000,
      "gid": 1000
    },
    {
      "source": "./local",
      "target": "/app/local",
      "read_only": true,
      "selinux": "z"
    }
  ]
}
```

**Note:** `uid`/`gid` options only work with named volumes (sets ownership when volume is created). Bind mounts inherit permissions from the host filesystem.

## Install/Uninstall

```bash
./vibecon.py -i          # Install symlink to ~/.local/bin
./vibecon.py -u          # Remove symlink
```
