# Skill-specific image for GitHub skill evals.
# Extends the OpenHands base with the gh CLI pre-installed.
#
# Build from repo root:
#   docker build -t openhands-eval-github:latest -f skills/github-skill/Dockerfile .
FROM openhands-eval:latest

# Install gh CLI (GitHub's official CLI)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
