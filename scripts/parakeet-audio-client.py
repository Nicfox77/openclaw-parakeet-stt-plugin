#!/usr/bin/env python3
"""
Parakeet Audio Client for OpenClaw
Transcribes audio files using the Parakeet lazy daemon.
Outputs transcript to stdout (OpenClaw CLI model requirement).
"""
import json
import os
import socket
import subprocess
import sys
import time

SOCKET_PATH = "/tmp/parakeet-lazy.sock"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON_PATH = os.path.join(SCRIPT_DIR, "parakeet-lazy-daemon.py")
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

def ensure_daemon():
    """Check if daemon is running, start it if not."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
        return  # daemon already running
    except Exception:
        pass
    # Start daemon in background with venv Python
    python_exe = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
    try:
        subprocess.Popen(
            [python_exe, DAEMON_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        time.sleep(1)  # give it a moment to start
    except Exception as e:
        print(f"Failed to start daemon: {e}", file=sys.stderr)
        sys.exit(1)

def query_daemon(audio_path):
    """Query the daemon for transcription."""
    for attempt in range(3):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(SOCKET_PATH)
                request = {"action": "transcribe", "audio_path": audio_path}
                s.sendall(json.dumps(request).encode() + b"\n")
                response_data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    if b"\n" in chunk:
                        break
            if response_data:
                response = json.loads(response_data.strip())
                if "text" in response:
                    return response["text"]
                else:
                    print(response.get("error", "Unknown error"), file=sys.stderr)
                    return None
            else:
                time.sleep(0.5)
        except Exception as e:
            if attempt == 2:
                print(f"Daemon communication failed: {e}", file=sys.stderr)
                return None
            time.sleep(0.5)
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parakeet-audio-client.py <audio_path>", file=sys.stderr)
        sys.exit(1)
    
    audio_path = sys.argv[1]
    
    # Start daemon if needed
    ensure_daemon()
    
    # Get transcription
    transcript = query_daemon(audio_path)
    
    if transcript:
        # Output transcript to stdout (OpenClaw reads stdout for CLI transcribers)
        print(transcript)
        sys.exit(0)
    else:
        print("Transcription failed", file=sys.stderr)
        sys.exit(1)
