---
name: parakeet
description: Parakeet speech-to-text system. Provides fast CPU-based transcription using Parakeet TDT INT8 models. Use when checking transcription status or troubleshooting audio issues.
---

# Parakeet STT

Fast CPU-based speech-to-text using NVIDIA's Parakeet TDT INT8 models.

## Model Versions

| Version | Description | Languages |
|---------|-------------|-----------|
| **V2** | English optimized | English (higher accuracy) |
| **V3** | Multilingual | 25 European languages + auto-detect |

## Install / Switch Model

```bash
# Install V2 (English optimized - default)
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v2

# Install/switch to V3 (Multilingual)
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v3
```

The install script:
- Downloads the pre-quantized INT8 model (~475MB)
- Sets up the Python virtual environment
- Creates a symlink at `~/.openclaw/tools/parakeet/model` pointing to the active model

## Status Check

```bash
openclaw parakeet:status
```

## How It Works

1. Audio messages are automatically transcribed before reaching the agent
2. First transcription loads the model (~3 seconds)
3. Model stays loaded for subsequent transcriptions
4. After 20 minutes of inactivity, model unloads to save memory

## Model Selection

The daemon automatically selects the model:

1. **Symlink** (`~/.openclaw/tools/parakeet/model`) - set by install.sh
2. **Environment variable** `PARAKEET_MODEL_VERSION=v2` or `v3`
3. **Auto-detect** - looks for model-v2, then model-v3 directories

## Troubleshooting

### Check if configured

Look at `tools.media.audio.models` in openclaw.json - it should point to the parakeet client script.

### Check daemon status

```bash
# Check if daemon socket exists
ls -la /tmp/parakeet-lazy.sock

# Watch logs
openclaw logs --follow | grep -i parakeet
```

### Model not found error

Run the install script:
```bash
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v2
```

### Manual transcription test

```bash
# Activate venv and test
source ~/.openclaw/tools/parakeet/venv/bin/activate
python ~/.openclaw/tools/parakeet/parakeet_transcribe.py path/to/audio.ogg
```

## Configuration

In `plugins.entries.parakeet-stt`:
- `enabled`: Enable/disable
- `modelVersion`: "v2" or "v3" (informational - actual switching via install.sh)
- `inactivityTimeoutMin`: Minutes before unloading (default: 20)
