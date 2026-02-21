#!/bin/bash
# Parakeet TDT INT8 Model Installer
# Downloads pre-quantized INT8 models from the Handy project
# https://github.com/cjpais/Handy

set -e

# Configuration
PARAKEET_DIR="${PARAKEET_DIR:-$HOME/.openclaw/tools/parakeet}"
VENV_DIR="$PARAKEET_DIR/.venv"

# Model URLs (from Handy project)
MODEL_URLS_V2="https://blob.handy.computer/parakeet-v2-int8.tar.gz"
MODEL_URLS_V3="https://blob.handy.computer/parakeet-v3-int8.tar.gz"

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
    
    if command -v wget &> /dev/null; then
        wget -O "$TMP_TAR" "$MODEL_URL"
    elif command -v curl &> /dev/null; then
        curl -L -o "$TMP_TAR" "$MODEL_URL"
    else
        echo "Error: wget or curl required for download"
        exit 1
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
echo "OpenClaw config (already configured):"
echo '  tools.media.audio.models → parakeet-audio-client.py'
