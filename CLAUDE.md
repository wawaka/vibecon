# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecon is a Python CLI tool that creates persistent, isolated Docker containers for running Claude Code (and other AI coding assistants) safely. Each workspace directory gets its own container that persists across sessions.

## Commands

```bash
# Install/uninstall the vibecon symlink
./vibecon.py -i          # Install to ~/.local/bin/vibecon
./vibecon.py -u          # Uninstall

# Initialize project
vibecon -r .             # Initialize .vibecon.json in current dir
vibecon -r /path/to/dir  # Initialize in specified directory

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

Vibecon **requires** a `.vibecon.json` file with a `root` field to define the project root. This file is searched for starting from the current directory up through parent directories.

### Required: Project Root Config

Every project must have a `.vibecon.json` with a `root` field:

```json
{
  "root": "/workspace",
  "mounts": [...]
}
```

The `root` field specifies the container path where the project directory is mounted. Running `vibecon` without a valid root config will exit with an error.

### Config File Locations

- `./.vibecon.json` (or parent directories) - **Required**, must contain `root` field
- `~/.vibecon.json` - Global config (optional, extra mounts for all projects)

Configs are merged: global mounts first, then project mounts appended.

### Working Directory

When running from a subdirectory within a project, vibecon:
1. Finds the project root by searching up for `.vibecon.json` with `root`
2. Uses project root for container naming (same container for all subdirs)
3. Sets the working directory inside the container to match your relative position

Example:
- Host cwd: `/Users/vlk/projects/myproject/src/components`
- Project root: `/Users/vlk/projects/myproject`
- Container mount root: `/workspace`
- Container workdir: `/workspace/src/components`

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
  "root": "/workspace",
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"}
  ]
}
```

#### Monorepo with multiple workspaces
```json
{
  "root": "/workspace",
  "mounts": [
    {"type": "anonymous", "target": "/workspace/node_modules"},
    {"type": "anonymous", "target": "/workspace/frontend/node_modules"},
    {"type": "anonymous", "target": "/workspace/backend/node_modules"}
  ]
}
```

#### Global config (~/.vibecon.json) - shared cache volumes
```json
{
  "mounts": [
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "volume", "source": "pnpm_store", "target": "/home/node/.local/share/pnpm", "global": true}
  ]
}
```

Note: Global config does not need a `root` field since it's for extra mounts only.

#### Bind mounts for config files
```json
{
  "root": "/workspace",
  "mounts": [
    {"type": "bind", "source": "~/.aws", "target": "/home/node/.aws", "read_only": true},
    {"type": "bind", "source": "./config", "target": "/app/config", "read_only": true}
  ]
}
```

#### Complete project setup
```json
{
  "root": "/workspace",
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

**Single-file CLI**: `vibecon.py` - All logic in one Python script (~840 lines)

**Container lifecycle**:
1. `find_project_root()` searches up directory tree for `.vibecon.json` with `root` field
2. `generate_container_name()` creates unique name from project root path + MD5 hash
3. `ensure_container_running()` handles create/restart/reuse logic
4. Containers run detached with `sleep infinity`, commands exec into them with `-w` for workdir

**Key functions**:
- `find_project_root()` - Searches for `.vibecon.json` with `root` field, returns (project_root, config, mount_root)
- `get_merged_config()` - Merges `~/.vibecon.json` global mounts + project config mounts
- `parse_mount()` - Parses mount objects into docker arguments (returns `-v` or `--mount` args)
- `sync_claude_config()` - Copies statusLine settings, CLAUDE.md, and commands/ dir from host `~/.claude/` to container
- `get_all_versions()` - Fetches latest versions of gemini-cli, codex from npm, and Go from golang.org
- `build_image()` - Builds Docker image with composite version tag
- `detect_worktree()` - Detects git worktrees and returns path to main `.git` directory

**Docker image** (`Dockerfile`):
- Base: `node:24` with zsh, git, fzf, gh, delta, nano, vim, curl, make, build-essential
- Go toolchain with gopls, delve, golangci-lint, goimports
- Installs Claude Code via official installer, plus `@google/gemini-cli` and `@openai/codex` from npm
- Runs as non-root `node` user (uid 1000)
- Entrypoint configures git from env vars on first run

## Git Worktree Support

Vibecon automatically detects and supports git worktrees. When you run vibecon from a worktree directory:

1. **Auto-detection**: Vibecon detects that `.git` is a file (not a directory) and parses it to find the main repository's `.git` directory
2. **Automatic mounting**: The main `.git` directory is mounted at its original absolute path inside the container
3. **Transparent operation**: Git commands work normally inside the container because path references in the worktree's `.git` file resolve correctly

### How it works

In a git worktree, the `.git` file contains a reference like:
```
gitdir: /home/user/main-repo/.git/worktrees/feature-branch
```

Vibecon parses this to find `/home/user/main-repo/.git` and mounts it at the same path inside the container. This allows git operations (commit, push, pull, etc.) to work seamlessly.

### Limitations

- Each worktree gets its own container (they don't share)
- The main repository's `.git` directory must be accessible from the host
- If running multiple containers accessing the same `.git` directory, be aware of potential lock contention

## Development Guidelines

### Docker Container Naming
- Do not shorten Docker container names - always use full path + full hash
- Container names follow pattern: `vibecon-{md5-hash}-{full-sanitized-path}`

### Mount Implementation Details

The `parse_mount()` function handles three mount types differently:

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
