# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecon is a TypeScript CLI tool built with Bun that creates persistent, isolated Docker containers for running Claude Code (and other AI coding assistants) safely. Each workspace directory gets its own container that persists across sessions.

## Commands

```bash
# Install dependencies and build
bun install
bun run build              # Creates compiled binary ./vibecon

# Development
bun run src/index.ts       # Run directly with Bun
bun run dev                # Run with watch mode

# Install/uninstall the vibecon symlink
./vibecon -i               # Install to ~/.local/bin/vibecon
vibecon -u                 # Uninstall

# Container operations
vibecon                    # Start claude in container (default command)
vibecon zsh                # Run zsh in container
vibecon gemini             # Run Gemini CLI
vibecon codex              # Run OpenAI Codex
vibecon -b                 # Rebuild image if npm versions changed
vibecon -B                 # Force rebuild regardless of versions
vibecon -k                 # Stop container (can restart later)
vibecon -K                 # Destroy container permanently
```

## Configuration Files

Vibecon supports JSON config files for extra mounts:
- `~/.vibecon.json` - Global config (applies to all projects)
- `./.vibecon.json` - Project config (applies to current workspace)

Configs are merged: global mounts first, then project mounts appended.

### Mount Syntax

All mounts must be objects with an explicit `type` field. Three types are supported:

#### type="bind" - Bind mount from host to container

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"bind"` |
| `source` | Yes | Host path (`./`, `../`, `~/`, or absolute) |
| `target` | Yes | Container path |
| `read_only` | No | Boolean, default false |
| `selinux` | No | `"z"` (shared) or `"Z"` (private) |

#### type="volume" - Named Docker volume

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"volume"` |
| `source` | Yes | Volume name |
| `target` | Yes | Container path |
| `global` | No | If true, volume name used as-is; if false (default), prefixed with container name |
| `read_only` | No | Boolean, default false |
| `uid` | No | Owner UID (integer) - **WARNING: uses tmpfs, data is ephemeral** |
| `gid` | No | Owner GID (integer) - **WARNING: uses tmpfs, data is ephemeral** |
| `selinux` | No | `"z"` (shared) or `"Z"` (private) |

#### type="anonymous" - Anonymous Docker volume

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"anonymous"` |
| `target` | Yes | Container path |
| `read_only` | No | Boolean, default false |
| `uid` | No | Owner UID (integer) - uses tmpfs backing |
| `gid` | No | Owner GID (integer) - uses tmpfs backing |

### Example Configs

#### Basic node_modules isolation
```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"}
  ]
}
```

#### Monorepo with multiple workspaces
```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "anonymous", "target": "/workspace/frontend/node_modules"},
    {"type": "anonymous", "target": "/workspace/backend/node_modules"}
  ]
}
```

#### Shared cache volumes (global)
```json
{
  "mounts": [
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "volume", "source": "pnpm_store", "target": "/home/node/.local/share/pnpm", "global": true}
  ]
}
```

#### Bind mounts for config files
```json
{
  "mounts": [
    {"type": "bind", "source": "~/.aws", "target": "/home/node/.aws", "read_only": true},
    {"type": "bind", "source": "./config", "target": "/app/config", "read_only": true}
  ]
}
```

#### Complete project setup
```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "volume", "source": "app_data", "target": "/app/data"},
    {"type": "bind", "source": "~/.env.local", "target": "/workspace/.env", "read_only": true}
  ]
}
```

### Path Resolution (for bind mounts)
- `./` and `../` - relative to project root
- `~/` - user's home directory
- `/` - absolute path

### Important: uid/gid Uses tmpfs

When `uid` or `gid` is specified on volumes, Docker requires tmpfs-backed storage to set ownership at mount time. **This means data is NOT persisted** across container restarts.

For persistent volumes, omit uid/gid - the `node` user (uid 1000) in the container will own files it creates.

### Config Changes Require Container Recreation

Mounts are only applied at container creation. After modifying `.vibecon.json`:
```bash
vibecon -K    # Destroy container
vibecon       # Creates new container with updated mounts
```

## Architecture

**Modular TypeScript CLI** built with Bun for fast execution and easy compilation.

**Project Structure**:
```
vibecon/
├── src/
│   ├── index.ts        # Main entry point and CLI
│   ├── types.ts        # TypeScript type definitions
│   ├── config.ts       # Config loading and mount parsing
│   ├── docker.ts       # Docker container operations
│   ├── versions.ts     # Version checking and image building
│   ├── sync.ts         # Claude config syncing
│   ├── install.ts      # Symlink installation
│   └── utils.ts        # Utility functions (timezone, git, etc.)
├── package.json        # Bun project config
├── tsconfig.json       # TypeScript configuration
├── Dockerfile          # Container image definition
├── CLAUDE.md           # This file
└── README.md           # User documentation
```

**Module Responsibilities**:
- `types.ts` - Shared TypeScript interfaces (MountSpec, VibeconConfig, Versions)
- `config.ts` - `loadConfig()`, `getMergedConfig()`, `parseMount()`
- `docker.ts` - Container lifecycle: `isContainerRunning()`, `containerExists()`, `startContainer()`, `ensureContainerRunning()`
- `versions.ts` - `getAllVersions()`, `makeCompositeTag()`, `buildImage()`
- `sync.ts` - `syncClaudeConfig()` for copying settings to container
- `install.ts` - `installSymlink()`, `uninstallSymlink()`
- `utils.ts` - `getHostTimezone()`, `getGitUserInfo()`, `findVibeconRoot()`, color codes

**Container lifecycle**:
1. `generateContainerName()` creates unique name from workspace path + MD5 hash
2. `ensureContainerRunning()` handles create/restart/reuse logic
3. Containers run detached with `sleep infinity`, commands exec into them

**Docker image** (`Dockerfile`):
- Base: `node:24` with zsh, git, fzf, gh, delta, nano, vim, curl, make, build-essential
- Go toolchain with gopls, delve, golangci-lint, goimports
- Installs Claude Code via official installer, plus `@google/gemini-cli` and `@openai/codex` from npm
- Runs as non-root `node` user (uid 1000)
- Entrypoint configures git from env vars on first run

## Development Guidelines

### Building and Running

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

# Type checking
bun run typecheck
```

### Docker Container Naming
- Do not shorten Docker container names - always use full path + full hash
- Container names follow pattern: `vibecon-{full-sanitized-path}-{full-md5-hash}`

### Mount Implementation Details

The `parseMount()` function in `src/config.ts` handles three mount types:

**Bind mounts**: Uses `-v source:target[:options]` syntax
- Options: `ro` for read-only, `z`/`Z` for SELinux

**Named volumes without uid/gid**: Uses `-v volume_name:target[:options]` syntax
- Volume name prefixed with container name unless `global: true`

**Volumes with uid/gid**: Uses `--mount` syntax with tmpfs backing
- Required because Docker's local driver only supports uid/gid with tmpfs
- Mount string: `type=volume,source=name,target=/path,volume-opt=type=tmpfs,volume-opt=device=tmpfs,"volume-opt=o=uid=X,gid=Y"`
- Quotes around `volume-opt=o=...` escape the comma in Docker's CSV parser

**Anonymous volumes**: Uses `-v /target` syntax (no source)
- With uid/gid: Same tmpfs approach as named volumes

### Testing Config Changes

After modifying mount handling code, test with:
```bash
# Destroy existing container
vibecon -K

# Create new container with mounts
vibecon zsh

# Inside container, verify mounts
mount | grep workspace
ls -la /workspace/node_modules
```

### TypeScript/Bun Conventions

- Use strict TypeScript configuration
- Prefer async/await over callbacks
- Use native argument parsing (no external CLI libraries)
- Use child_process spawn/exec for external commands
- Bun's built-in TypeScript support - no compilation needed for development
- `bun build --compile` for standalone binary distribution
