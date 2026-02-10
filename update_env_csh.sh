#!/usr/bin/env bash
# update_env_csh.sh — Update Env.csh paths to match current directory
# Equivalent of update_env_csh.bat but for native Linux (no WSL)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/Env.csh"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] Env.csh not found at: $ENV_FILE"
    exit 1
fi

# Prompt for project path (default: current script directory)
read -r -p "Enter Linux project path [$SCRIPT_DIR]: " USER_PATH
USER_PATH="${USER_PATH:-$SCRIPT_DIR}"

# Update WSL_PROJECT_PATH in Env.csh
sed -i "s|^WSL_PROJECT_PATH\s*=.*|WSL_PROJECT_PATH = $USER_PATH|" "$ENV_FILE"

# Clear WIN_PROJECT_PATH since we're on native Linux
sed -i "s|^WIN_PROJECT_PATH\s*=.*|WIN_PROJECT_PATH = (not applicable on native Linux)|" "$ENV_FILE"

echo
echo "Env.csh updated:"
echo "  WSL_PROJECT_PATH = $USER_PATH"
echo
echo "Done."
