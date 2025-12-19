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

## Install/Uninstall

```bash
./vibecon.py -i          # Install symlink to ~/.local/bin
./vibecon.py -u          # Remove symlink
```
