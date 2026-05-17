#!/usr/bin/env bash
set -euo pipefail

mkdir -p /workspace "$HOME/.claude"
chown -R "$(id -u):$(id -g)" /workspace "$HOME/.claude" 2>/dev/null || true
sed -i 's|/root/.oh-my-zsh|/home/vscode/.oh-my-zsh|g' ~/.zshrc ~/.bashrc
echo "eval \$(fnm env)" >> "/home/vscode/.zshrc"

SSH_KEY="$HOME/.ssh/id_rsa_intellidog"
if [ -f "$SSH_KEY" ]; then
    chmod 600 "$SSH_KEY"
    ssh-keyscan -H github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null
    git config --global core.sshCommand "ssh -i $SSH_KEY -o IdentitiesOnly=yes"
fi

echo "==> Container ready. Activate your venv and run 'make install'"
