# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecon is a Python CLI tool that creates persistent, isolated Docker containers for running Claude Code (and other AI coding assistants) safely. Each workspace directory gets its own container that persists across sessions.

## Commands

```bash
# Install/uninstall the vibecon symlink
./vibecon.py -i          # Install to ~/.local/bin/vibecon
./vibecon.py -u          # Uninstall

# Container operations
vibecon                  # Start claude in container (default command)
vibecon zsh              # Run zsh in container
vibecon -b               # Rebuild image if npm versions changed
vibecon -B               # Force rebuild regardless of versions
vibecon -k               # Stop container (can restart later)
vibecon -K               # Destroy container permanently
```

## Configuration Files

Vibecon supports JSON config files for extra mounts:
- `~/.vibecon.json` - Global config (applies to all projects)
- `./.vibecon.json` - Project config (applies to current workspace)

Configs are merged: global first, then project overrides.

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
| `uid` | No | Owner UID (integer) |
| `gid` | No | Owner GID (integer) |
| `selinux` | No | `"z"` (shared) or `"Z"` (private) |

#### type="anonymous" - Anonymous Docker volume

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `"anonymous"` |
| `target` | Yes | Container path |
| `read_only` | No | Boolean, default false |

### Example Config

```json
{
  "mounts": [
    {"type": "anonymous", "target": "/workspace/.temp"},
    {"type": "volume", "source": "node_modules", "target": "/workspace/node_modules"},
    {"type": "volume", "source": "npm_cache", "target": "/home/node/.npm", "global": true},
    {"type": "bind", "source": "./data", "target": "/data", "read_only": true},
    {"type": "volume", "source": "mydata", "target": "/data", "uid": 1000, "gid": 1000}
  ]
}
```

### Path Resolution (for bind mounts)
- `./` and `../` - relative to project root
- `~/` - user's home directory
- `/` - absolute path

## Architecture

**Single-file CLI**: `vibecon.py` - All logic in one Python script (~670 lines)

**Container lifecycle**:
1. `generate_container_name()` creates unique name from workspace path + MD5 hash
2. `ensure_container_running()` handles create/restart/reuse logic
3. Containers run detached with `sleep infinity`, commands exec into them

**Key functions**:
- `sync_claude_config()` - Copies statusLine settings and CLAUDE.md from host `~/.claude/` to container
- `get_all_versions()` - Fetches latest versions of claude-code, gemini-cli, codex from npm
- `build_image()` - Builds Docker image with composite version tag
- `get_merged_config()` - Loads and merges `~/.vibecon.json` + `./.vibecon.json`
- `parse_mount()` - Parses mount objects into docker mount arguments (returns `-v` or `--mount` args)

**Docker image** (`Dockerfile`):
- Base: `node:24` with zsh, git, fzf, gh, delta
- Installs 3 AI CLI tools: `@anthropic-ai/claude-code`, `@google/gemini-cli`, `@openai/codex`
- Runs as non-root `node` user
- Entrypoint configures git from env vars on first run

## Development Guidelines

### Docker Container Naming
- Do not shorten Docker container names - always use full path + full hash
- Container names follow pattern: `vibecon-{full-sanitized-path}-{full-md5-hash}`
