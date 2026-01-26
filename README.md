# vibecon

Persistent Docker containers for Claude Code, Gemini CLI, and OpenAI Codex.

## Quick Start

```bash
# Clone and build
git clone <repo-url>
cd vibecon
bun install
bun run build

# Install
./vibecon -i
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
- Runs as non-root `node` user (uid 1000)
- Git config inherited from host

## Configuration

Optional config files: `~/.vibecon.json` (global) and `./.vibecon.json` (project).

Configs are merged: global mounts first, then project mounts appended.

### Mount Types

All mounts must be objects with an explicit `type` field:

| Type | Description |
|------|-------------|
| `bind` | Mount host directory into container |
| `volume` | Named Docker volume (persists across container recreations) |
| `anonymous` | Ephemeral volume (cleared on container recreation) |

### Bind Mounts

Mount a host directory into the container.

```json
{
  "mounts": [
    {"type": "bind", "source": "./data", "target": "/app/data"},
    {"type": "bind", "source": "~/shared", "target": "/shared"},
    {"type": "bind", "source": "/etc/hosts", "target": "/etc/hosts", "read_only": true}
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"bind"` |
| `source` | Yes | Host path (`./`, `../`, `~/`, or absolute) |
| `target` | Yes | Container path |
| `read_only` | No | Mount as read-only (default: false) |
| `selinux` | No | SELinux label: `"z"` (shared) or `"Z"` (private) |

### Named Volumes

Docker-managed volumes that persist independently of containers.

```json
{
  "mounts": [
    {"type": "volume", "source": "node_modules", "target": "/workspace/node_modules"},
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true}
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"volume"` |
| `source` | Yes | Volume name |
| `target` | Yes | Container path |
| `global` | No | If true, use volume name as-is; if false (default), prefix with container name for isolation |
| `read_only` | No | Mount as read-only (default: false) |
| `uid` | No | Owner UID - **WARNING: uses tmpfs, data is ephemeral** |
| `gid` | No | Owner GID - **WARNING: uses tmpfs, data is ephemeral** |
| `selinux` | No | SELinux label: `"z"` (shared) or `"Z"` (private) |

**Volume naming:**
- `global: false` (default): Volume named `{container-name}_{source}` - isolated per project
- `global: true`: Volume named exactly `{source}` - shared across all projects

### Anonymous Volumes

Ephemeral volumes that are cleared when the container is recreated.

```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "anonymous", "target": "/tmp/cache"}
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"anonymous"` |
| `target` | Yes | Container path |
| `read_only` | No | Mount as read-only (default: false) |
| `uid` | No | Owner UID - uses tmpfs backing |
| `gid` | No | Owner GID - uses tmpfs backing |

**Use cases:**
- Isolate `node_modules` from host filesystem for performance
- Temporary build directories
- Caches that can be regenerated

## Comprehensive Examples

### Node.js Project with Isolated node_modules

Isolate node_modules for better performance (especially on macOS):

```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"}
  ]
}
```

### Monorepo with Multiple node_modules

For pnpm/npm workspaces:

```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "anonymous", "target": "/workspace/frontend/node_modules"},
    {"type": "anonymous", "target": "/workspace/backend/node_modules"},
    {"type": "anonymous", "target": "/workspace/packages/shared/node_modules"}
  ]
}
```

### Shared npm Cache Across Projects

Use a global volume to share npm cache:

```json
{
  "mounts": [
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "volume", "source": "pnpm_store", "target": "/home/node/.local/share/pnpm", "global": true}
  ]
}
```

### Read-Only Config Files

Mount configuration files from host:

```json
{
  "mounts": [
    {"type": "bind", "source": "~/.aws", "target": "/home/node/.aws", "read_only": true},
    {"type": "bind", "source": "~/.ssh", "target": "/home/node/.ssh", "read_only": true},
    {"type": "bind", "source": "./config.json", "target": "/app/config.json", "read_only": true}
  ]
}
```

### Persistent Data Volume

Keep data across container recreations:

```json
{
  "mounts": [
    {"type": "volume", "source": "app_data", "target": "/app/data"},
    {"type": "volume", "source": "postgres_data", "target": "/var/lib/postgresql/data"}
  ]
}
```

### Complete Project Setup

```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "volume", "source": "app_data", "target": "/app/data"},
    {"type": "bind", "source": "~/.env.local", "target": "/workspace/.env", "read_only": true},
    {"type": "bind", "source": "./scripts", "target": "/scripts", "read_only": true}
  ]
}
```

### SELinux Environments (RHEL/Fedora)

On SELinux-enabled systems, add labels:

```json
{
  "mounts": [
    {"type": "bind", "source": "./data", "target": "/data", "selinux": "z"},
    {"type": "bind", "source": "./secrets", "target": "/secrets", "selinux": "Z", "read_only": true}
  ]
}
```

- `z`: Shared label - multiple containers can access
- `Z`: Private label - only this container can access

## Important Notes

### uid/gid Warning

When `uid` or `gid` is specified on volumes, vibecon uses tmpfs-backed storage to set ownership. **This means data is stored in memory and is NOT persisted** across container restarts.

For persistent volumes with correct ownership, omit uid/gid - the `node` user (uid 1000) in the container will own files it creates.

### Config Changes Require Container Recreation

Mount configuration is only applied when the container is created. After modifying `.vibecon.json`:

```bash
vibecon -K    # Destroy container
vibecon       # Creates new container with updated mounts
```

### Path Resolution for Bind Mounts

- `./path` - Relative to project root (where you run vibecon)
- `../path` - Parent directories allowed
- `~/path` - User's home directory
- `/path` - Absolute path

## Development

```bash
# Install dependencies
bun install

# Run directly with Bun (development)
bun run src/index.ts [args]

# Run with watch mode
bun run dev

# Build compiled binary
bun run build

# Run compiled binary
./vibecon [args]
```

## Install/Uninstall

```bash
bun run build
./vibecon -i             # Install symlink to ~/.local/bin
vibecon -u               # Remove symlink
```
