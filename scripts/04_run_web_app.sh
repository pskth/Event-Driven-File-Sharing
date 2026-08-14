#!/bin/bash
set -e

# Load configuration from .env file
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

WEB_APP_DIR="$(dirname "$0")/../src/web_app"

echo "Installing web app dependencies..."
pip install -r "$WEB_APP_DIR/requirements.txt" --quiet

echo "Starting SecureShare web app on http://localhost:${WEB_APP_PORT:-5000} ..."
python "$WEB_APP_DIR/server.py"
