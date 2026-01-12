FROM node:24

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest
ARG GEMINI_CLI_VERSION=latest
ARG OPENAI_CODEX_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  jq \
  nano \
  vim \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure default node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R node:node /usr/local/share

ARG USERNAME=node

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories and set permissions
RUN mkdir -p /workspace /home/node/.claude && \
  chown -R node:node /workspace /home/node/.claude

WORKDIR /workspace

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Create entrypoint script to configure git from environment variables
RUN echo '#!/bin/sh\n\
if [ -n "$GIT_USER_NAME" ] && [ ! -f ~/.git-configured ]; then\n\
  git config --global user.name "$GIT_USER_NAME"\n\
  git config --global user.email "$GIT_USER_EMAIL"\n\
  touch ~/.git-configured\n\
  echo "Git configured: $GIT_USER_NAME <$GIT_USER_EMAIL>"\n\
fi\n\
exec "$@"' > /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

# Set up non-root user
USER node

# Install global packages
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Set the default shell to zsh rather than sh
ENV SHELL=/bin/zsh

# Set the default editor and visual
ENV EDITOR=nano
ENV VISUAL=nano

# Fix terminal colors for Claude Code and other CLI tools
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

# Default powerline10k theme
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh" \
  -x

# Install package managers and common Node.js tools
RUN npm install -g \
  pnpm \
  yarn \
  typescript \
  ts-node \
  npm-check-updates

# Install AI coding assistants
RUN npm install -g \
  @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
  @google/gemini-cli@${GEMINI_CLI_VERSION} \
  @openai/codex@${OPENAI_CODEX_VERSION}

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sleep", "infinity"]
