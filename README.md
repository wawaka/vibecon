# 🎯 vibecon

> **Persistent Docker container environment for Claude Code**

Vibecon creates isolated, persistent Docker containers for each of your projects, allowing you to run Claude Code safely without touching your host system. Each workspace gets its own container that persists across sessions, maintaining state while keeping your projects isolated.

---

## ✨ Quick Start

Get up and running in 4 simple steps:

```bash
# 1. Clone this repository
git clone <your-repo-url>
cd vibecon

# 2. Install the symlink
./vibecon.py -i

# 3. Add ~/.local/bin to your PATH (if not already)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 4. Navigate to your project and launch vibecon
cd /path/to/your/project
vibecon
```

When Claude starts, authorize it with your Anthropic API key, and you're ready to vibe code safely! 🚀

---

## 🎨 Features

### 🔒 **Isolated Environments**
Each workspace directory gets its own persistent container, keeping projects completely isolated from each other and your host system.

### 📦 **Smart Container Management**
Containers persist across sessions and are automatically reused. No unnecessary rebuilds or state loss.

### 🏗️ **Intelligent Image Building**
- Only builds Docker images when they don't exist
- Uses the latest version of `@anthropic-ai/claude-code` from npm
- Tags images with both `latest` and specific version numbers
- Pass version as build argument for reproducible builds

### 🔗 **Symlink Installation**
Install vibecon system-wide with a simple command, making it accessible from anywhere.

### 🎯 **Container Naming**
Containers are named based on your workspace path with a hash, making them easy to identify and manage.

### ⚡ **Zero Configuration**
Just run `vibecon` in any directory, and it handles everything automatically.

---

## 📖 Usage

### Installation & Setup

| Command | Description |
|---------|-------------|
| `./vibecon.py -i` or `--install` | Install symlink to `~/.local/bin/vibecon` |
| `./vibecon.py -u` or `--uninstall` | Remove the symlink |

### Container Operations

| Command | Description |
|---------|-------------|
| `vibecon` | Start Claude Code in container (creates container if needed) |
| `vibecon -b` or `--build` | Force rebuild image with latest claude-code version from npm |
| `vibecon -k` or `--kill` | Kill and remove container for current workspace |
| `vibecon [command]` | Run custom command in container (e.g., `vibecon zsh`) |

### Examples

```bash
# Start Claude Code (default behavior)
vibecon

# Force rebuild with latest claude-code version
vibecon -b

# Run a shell in the container
vibecon zsh

# Execute arbitrary commands
vibecon ls -la
vibecon git status

# Kill the container for this workspace
vibecon -k
```

---

## 🔧 How It Works

### Container Lifecycle

1. **First Run**: When you run `vibecon` in a directory for the first time:
   - Checks if Docker image exists (if not, builds it)
   - Creates a new container specific to your workspace
   - Mounts your current directory at `/workspace`
   - Starts the container in detached mode
   - Executes your command (default: Claude Code)

2. **Subsequent Runs**: On future runs in the same directory:
   - Reuses the existing container
   - Maintains all state (command history, claude config, etc.)
   - No rebuild or recreation needed

3. **Different Directories**: Each workspace gets its own container:
   - Complete isolation between projects
   - Independent environments and dependencies
   - No cross-contamination

### Container Naming

Containers are named using the pattern: `vibecon-{sanitized-path}-{hash}`

For example:
- `/home/user/projects/myapp` → `vibecon-home-user-projects-myapp-a1b2c3d4`
- `/workspace` → `vibecon-workspace-e5f6g7h8`

The hash ensures uniqueness even for similar path names.

### Image Versioning

When you run `vibecon -b`:
- Fetches the latest version of `@anthropic-ai/claude-code` from npm registry
- Builds the image with that specific version as a build argument
- Tags the image with both:
  - `vibecon:latest` (always points to most recent build)
  - `vibecon:{version}` (specific version tag, e.g., `vibecon:2.0.67`)

This allows you to:
- Always use the latest version
- Roll back to specific versions if needed
- Track which claude-code version each image contains

---

## 🛠️ Technical Details

### Container Configuration

- **Base Image**: `node:20`
- **Default User**: `node` (non-root)
- **Working Directory**: `/workspace` (mounted from host)
- **Default Shell**: `zsh` with oh-my-zsh
- **Terminal**: Full color support (256-color + truecolor)
- **Hostname**: `vibecon`

### Included Tools

The container comes pre-configured with:
- **Development**: git, gh (GitHub CLI), nano, vim
- **Shell**: zsh with fzf, git plugin
- **Utilities**: less, procps, sudo, unzip, jq
- **Network**: iptables, ipset, iproute2, dnsutils
- **Diff**: git-delta for beautiful diffs
- **Claude Code**: Latest version from npm

### Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `TERM` | `xterm-256color` | Terminal capabilities |
| `COLORTERM` | `truecolor` | 24-bit color support |
| `SHELL` | `/bin/zsh` | Default shell |
| `EDITOR` | `nano` | Default editor |
| `DEVCONTAINER` | `true` | Indicates container environment |

### Volume Mounts

Your current working directory is mounted at `/workspace` in the container, giving Claude Code full access to your project files while keeping everything else isolated.

---

## 🔐 Security & Safety

### Why Vibecon?

Running AI coding assistants with code execution capabilities can be risky. Vibecon provides:

- **Sandboxed Execution**: All code runs in isolated Docker containers
- **No Host Access**: Claude can't access files outside your project directory
- **Per-Project Isolation**: Each workspace is completely separate
- **Easy Cleanup**: Remove containers with a single command (`vibecon -k`)
- **Version Control**: Track exactly which claude-code version you're running

### Best Practices

1. **Review Before Commit**: Always review changes before committing
2. **Use Version Control**: Keep your work in git for easy rollback
3. **Separate Environments**: Use different workspaces for different projects
4. **Clean Up**: Use `vibecon -k` to remove containers you no longer need
5. **Update Regularly**: Run `vibecon -b` to get the latest claude-code version

---

## 🤝 Typical Workflow

Here's how a typical session with vibecon looks:

```bash
# Start your day
cd ~/projects/my-awesome-app
vibecon

# Claude starts up - authorize if first time
# API Key: sk-ant-...

# Work on your project with Claude
# Claude Code runs commands, edits files, helps you code

# When done, just exit (Ctrl+D or 'exit')
# Container stays running in the background

# Next day - instant resume
vibecon  # Picks up right where you left off!

# Clean up when project is done
vibecon -k  # Removes this workspace's container
```

---

## 📝 Requirements

- **Docker**: Must be installed and running
- **Python**: 3.6+ (for the vibecon script)
- **npm**: For fetching claude-code version info
- **Linux/macOS**: Tested on Linux, should work on macOS

---

## 🎭 Philosophy

Vibecon follows these principles:

1. **Simplicity**: One command to rule them all
2. **Safety**: Isolated environments protect your system
3. **Persistence**: Don't lose your work or state
4. **Efficiency**: Reuse containers, avoid unnecessary rebuilds
5. **Transparency**: Clear naming and versioning

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🙏 Acknowledgments

Built with:
- [Docker](https://www.docker.com/) - Container platform
- [Claude Code](https://github.com/anthropics/anthropic-quickstarts/tree/main/claude-code) - AI coding assistant
- [Node.js](https://nodejs.org/) - JavaScript runtime
- [zsh](https://www.zsh.org/) - Shell

---

**Happy vibing! 🎵✨**

