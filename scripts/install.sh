#!/bin/bash
# Parakeet TDT INT8 Model Installer
# Downloads pre-quantized INT8 models from the Handy project
# https://github.com/cjpais/Handy

set -e

# Configuration
PARAKEET_DIR="${PARAKEET_DIR:-$HOME/.openclaw/tools/parakeet}"
VENV_DIR="$PARAKEET_DIR/.venv"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

# Model URLs (GitHub release - mirrored from Handy project)
# Fallback to Handy if GitHub is unavailable
MODEL_URLS_V2="https://github.com/Nicfox77/openclaw-parakeet-stt-plugin/releases/download/v1.0.0/parakeet-v2-int8.tar.gz"
MODEL_URLS_V2_FALLBACK="https://blob.handy.computer/parakeet-v2-int8.tar.gz"
MODEL_URLS_V3="https://github.com/Nicfox77/openclaw-parakeet-stt-plugin/releases/download/v1.0.0/parakeet-v3-int8.tar.gz"
MODEL_URLS_V3_FALLBACK="https://blob.handy.computer/parakeet-v3-int8.tar.gz"

# Default to V2 (English optimized)
VERSION="${1:-v2}"

# Validate version
if [[ "$VERSION" != "v2" && "$VERSION" != "v3" ]]; then
    echo "Usage: $0 [v2|v3]"
    echo "  v2 - English optimized (higher accuracy for English)"
    echo "  v3 - Multilingual (25 European languages, auto-detect)"
    exit 1
fi

# Select URL based on version
if [[ "$VERSION" == "v2" ]]; then
    MODEL_URL="$MODEL_URLS_V2"
    MODEL_DIR="$PARAKEET_DIR/model-v2"
    MODEL_SIZE="473MB"
    MODEL_DESC="English optimized"
else
    MODEL_URL="$MODEL_URLS_V3"
    MODEL_DIR="$PARAKEET_DIR/model-v3"
    MODEL_SIZE="478MB"
    MODEL_DESC="Multilingual (25 languages)"
fi

# Create symlink to active model
ACTIVE_MODEL_LINK="$PARAKEET_DIR/model"

echo "=== Parakeet TDT $VERSION INT8 Installer ==="
echo "Model: $MODEL_DESC"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

echo "Python version: $(python3 --version)"

# Create directories
mkdir -p "$PARAKEET_DIR"

# Create virtual environment (reuse existing if present)
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install minimal dependencies (Handy models just need onnxruntime + librosa)
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install onnxruntime librosa soundfile

# Download and extract model if not present
if [ ! -d "$MODEL_DIR" ] || [ ! -f "$MODEL_DIR/model.onnx" ]; then
    echo ""
    echo "Downloading Parakeet TDT $VERSION model (~$MODEL_SIZE)..."
    echo "URL: $MODEL_URL"
    
    TMP_TAR="/tmp/parakeet-$VERSION-int8.tar.gz"
    
    download_model() {
        local url="$1"
        local output="$2"
        if command -v wget &> /dev/null; then
            wget -O "$output" "$url"
        elif command -v curl &> /dev/null; then
            curl -L -o "$output" "$url"
        else
            echo "Error: wget or curl required for download"
            return 1
        fi
    }
    
    # Try primary URL, fall back to Handy if it fails
    if ! download_model "$MODEL_URL" "$TMP_TAR"; then
        echo "Primary download failed, trying fallback..."
        FALLBACK_URL=""
        if [[ "$VERSION" == "v2" ]]; then
            FALLBACK_URL="$MODEL_URLS_V2_FALLBACK"
        else
            FALLBACK_URL="$MODEL_URLS_V3_FALLBACK"
        fi
        if ! download_model "$FALLBACK_URL" "$TMP_TAR"; then
            echo "Error: Failed to download model"
            exit 1
        fi
    fi
    
    echo "Extracting model..."
    mkdir -p "$MODEL_DIR"
    tar -xzf "$TMP_TAR" -C "$MODEL_DIR" --strip-components=1 2>/dev/null || {
        # If strip-components fails, try without it
        tar -xzf "$TMP_TAR" -C "$MODEL_DIR"
        # Move files from subdirectory if needed
        for subdir in "$MODEL_DIR"/*/; do
            if [ -d "$subdir" ]; then
                mv "$subdir"* "$MODEL_DIR/" 2>/dev/null || true
                rmdir "$subdir" 2>/dev/null || true
            fi
        done
    }
    rm -f "$TMP_TAR"
    
    echo "Model downloaded and extracted successfully"
else
    echo "Model already exists at $MODEL_DIR"
fi

# Update symlink to active model
rm -f "$ACTIVE_MODEL_LINK"
ln -s "$MODEL_DIR" "$ACTIVE_MODEL_LINK"
echo "Active model symlink: $ACTIVE_MODEL_LINK -> $MODEL_DIR"

# Copy scripts from extension to tools directory
SCRIPTS_SRC="$HOME/.openclaw/extensions/parakeet-stt/scripts"
for script in parakeet-lazy-daemon.py parakeet-audio-client.py parakeet_transcribe.py; do
    if [ -f "$SCRIPTS_SRC/$script" ]; then
        cp "$SCRIPTS_SRC/$script" "$PARAKEET_DIR/"
        chmod +x "$PARAKEET_DIR/$script"
        echo "Copied $script"
    fi
done

# Configure OpenClaw to use Parakeet for audio transcription
configure_openclaw() {
    if [ ! -f "$OPENCLAW_CONFIG" ]; then
        echo "Warning: OpenClaw config not found at $OPENCLAW_CONFIG"
        return 1
    fi
    
    # Check if parakeet is already configured
    if jq -e '.tools.media.audio.models[]? | select(.command | contains("parakeet"))' "$OPENCLAW_CONFIG" > /dev/null 2>&1; then
        echo "Parakeet already configured in OpenClaw"
        return 0
    fi
    
    echo "Configuring OpenClaw to use Parakeet for audio transcription..."
    
    # Use config.patch RPC for partial update (cleaner than modifying file directly)
    if command -v openclaw &> /dev/null; then
        local patch_json=$(cat <<EOF
{
  "patch": {
    "tools": {
      "media": {
        "audio": {
          "models": [
            {
              "type": "cli",
              "command": "$PARAKEET_DIR/parakeet-audio-client.py",
              "args": ["{{MediaPath}}", "{{OutputDir}}"]
            }
          ]
        }
      }
    }
  }
}
EOF
)
        openclaw gateway call config.patch --params "$patch_json" 2>/dev/null && {
            echo "Applied config.patch - Parakeet configured and gateway reloaded"
            return 0
        } || {
            echo "config.patch failed, falling back to file modification..."
        }
    fi
    
    # Fallback: modify config file directly if jq available
    if command -v jq &> /dev/null; then
        local tmp_config=$(mktemp)
        jq '.tools.media.audio.models += [{
            "type": "cli",
            "command": "'$PARAKEET_DIR'/parakeet-audio-client.py",
            "args": ["{{MediaPath}}", "{{OutputDir}}"]
        }]' "$OPENCLAW_CONFIG" > "$tmp_config" && mv "$tmp_config" "$OPENCLAW_CONFIG"
        echo "Added Parakeet to tools.media.audio.models (file modified directly)"
        echo "Note: Gateway will auto-reload, or run: openclaw gateway restart"
    else
        echo "Warning: jq not found, skipping automatic config"
        echo "Please manually add to openclaw.json:"
        echo '  tools.media.audio.models: [{"type": "cli", "command": "'$PARAKEET_DIR'/parakeet-audio-client.py", "args": ["{{MediaPath}}", "{{OutputDir}}"]}]'
    fi
}

configure_openclaw || true

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Version: $VERSION ($MODEL_DESC)"
echo "Model directory: $MODEL_DIR"
echo "Active model: $ACTIVE_MODEL_LINK"
echo "Virtual environment: $VENV_DIR"
echo ""
echo "To switch models, run:"
echo "  $0 v2  # English optimized"
echo "  $0 v3  # Multilingual"
echo ""
echo "Audio transcription is now configured and ready."
