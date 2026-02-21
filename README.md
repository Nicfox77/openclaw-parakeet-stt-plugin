# Parakeet STT for OpenClaw

Fast CPU-based speech-to-text using NVIDIA's Parakeet TDT INT8 models.

## Features

- **4x faster than real-time** (0.25x RTF)
- **CPU-only** - no GPU required
- **Two model versions:**
  - **V2** - English optimized (higher accuracy for English)
  - **V3** - Multilingual (25 European languages, auto-detect)
- **Lazy loading** - model loads on first transcription, unloads after inactivity

## Installation

### 1. Install the plugin

```bash
openclaw plugins install @nicfox77/parakeet-stt
```

### 2. Install a model

```bash
# English optimized (default)
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v2

# Or multilingual
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v3
```

This downloads the pre-quantized INT8 model (~475MB) from the [Handy project](https://github.com/cjpais/Handy).

### 3. Configure OpenClaw

Add to your `openclaw.json`:

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          {
            "type": "cli",
            "command": "/home/YOUR_USER/.openclaw/tools/parakeet/parakeet-audio-client.py",
            "args": ["{{MediaPath}}", "{{OutputDir}}"]
          }
        ]
      }
    }
  },
  "plugins": {
    "entries": {
      "parakeet-stt": {
        "enabled": true,
        "modelVersion": "v2"
      }
    }
  }
}
```

## Switching Models

```bash
# Switch to V2 (English)
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v2

# Switch to V3 (Multilingual)
~/.openclaw/extensions/parakeet-stt/scripts/install.sh v3
```

The install script updates a symlink, so the daemon automatically uses the new model on next load.

## CLI Commands

```bash
# Check status
openclaw parakeet:status

# Install model
openclaw parakeet:install v2
```

## Requirements

- Python 3.8+
- ~500MB disk space for model
- ~500MB RAM when model loaded

## Credits

- Models: [NVIDIA Parakeet TDT](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
- INT8 Quantization: [Handy](https://github.com/cjpais/Handy) by cjpais
- ONNX Runtime for inference

## License

MIT
