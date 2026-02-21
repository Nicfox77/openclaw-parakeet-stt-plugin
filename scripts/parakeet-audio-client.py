#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import time

SOCKET_PATH = "/tmp/parakeet-lazy.sock"
DAEMON_PATH = os.path.expanduser("~/.openclaw/tools/parakeet/parakeet-lazy-daemon.py")

def ensure_daemon():
    # Check if daemon socket exists and responsive
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
        return  # daemon already running
    except Exception:
        pass
    # Start daemon in background
    try:
        subprocess.Popen(
            [sys.executable, DAEMON_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        time.sleep(1)  # give it a moment to start
    except Exception as e:
        print(f"Failed to start daemon: {e}", file=sys.stderr)
        sys.exit(1)

def query_daemon(audio_path):
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
                    print(response["text"])
                    return 0
                else:
                    print(response.get("error", "Unknown error"), file=sys.stderr)
                    return 1
            else:
                time.sleep(0.5)
        except Exception as e:
            if attempt == 2:
                print(f"Daemon communication failed: {e}", file=sys.stderr)
                return 1
            time.sleep(0.5)
    return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parakeet-audio-client.py <audio_path> [output_dir]", file=sys.stderr)
        sys.exit(1)
    audio_path = sys.argv[1]
    # output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    ensure_daemon()
    sys.exit(query_daemon(audio_path))