# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecon is a Go CLI tool that creates persistent, isolated Docker containers for running Claude Code (and other AI coding assistants) safely. Each workspace directory gets its own container that persists across sessions.

## Commands

```bash
# Build the Go binary
go build -o vibecon .

# Install/uninstall the vibecon symlink
./vibecon -i             # Install to ~/.local/bin/vibecon
./vibecon -u             # Uninstall

# Container operations
vibecon                  # Start claude in container (default command)
vibecon zsh              # Run zsh in container
vibecon gemini           # Run Gemini CLI
vibecon codex            # Run OpenAI Codex
vibecon -b               # Rebuild image if npm versions changed
vibecon -B               # Force rebuild regardless of versions
vibecon -k               # Stop container (can restart later)
vibecon -K               # Destroy container permanently
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

**Go CLI Application**: Modular package structure

**Project structure**:
- `main.go` - Entry point and CLI argument parsing
- `internal/config/` - Config file loading and merging
- `internal/docker/` - Docker container lifecycle and image building
- `internal/mount/` - Mount specification parsing
- `internal/version/` - Concurrent version fetching from npm and golang.org
- `internal/sync/` - Claude config synchronization
- `internal/install/` - Symlink installation with PATH detection

**Container lifecycle**:
1. `GenerateContainerName()` creates unique name from workspace path + MD5 hash
2. `EnsureContainerRunning()` handles create/restart/reuse logic
3. Containers run detached with `sleep infinity`, commands exec into them

**Key features**:
- `GetMergedConfig()` - Loads and merges `~/.vibecon.json` + `./.vibecon.json`
- `ParseMount()` - Parses mount objects into docker arguments (returns `-v` or `--mount` args)
- `SyncClaudeConfig()` - Copies statusLine settings, CLAUDE.md, and commands/ dir from host `~/.claude/` to container
- `GetAllVersions()` - Fetches latest versions of gemini-cli, codex from npm, and Go from golang.org (concurrent)
- `BuildImage()` - Builds Docker image with composite version tag

**Docker image** (`Dockerfile`):
- Base: `node:24` with zsh, git, fzf, gh, delta, nano, vim, curl, make, build-essential
- Go toolchain with gopls, delve, golangci-lint, goimports
- Installs Claude Code via official installer, plus `@google/gemini-cli` and `@openai/codex` from npm
- Runs as non-root `node` user (uid 1000)
- Entrypoint configures git from env vars on first run

## Development Guidelines

### Docker Container Naming
- Do not shorten Docker container names - always use full path + full hash
- Container names follow pattern: `vibecon-{full-sanitized-path}-{full-md5-hash}`

### Mount Implementation Details

The `ParseMount()` function handles three mount types differently:

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
