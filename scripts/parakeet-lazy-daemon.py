#!/usr/bin/env python3
"""
Parakeet Lazy Daemon - Loads model on demand, unloads after inactivity.
Supports V2 (English) and V3 (Multilingual) model selection.
"""
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

# Add script directory to path to import ParakeetTDT
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Try to import, will fail if model not installed yet
try:
    from parakeet_transcribe import ParakeetTDT
except ImportError:
    print("Error: parakeet_transcribe not found. Run install.sh first.", file=sys.stderr)
    sys.exit(1)

SOCKET_PATH = "/tmp/parakeet-lazy.sock"
IDLE_TIMEOUT = 20 * 60  # 20 minutes

def get_model_path():
    """Determine which model to use based on config/env."""
    tools_dir = Path.home() / ".openclaw" / "tools" / "parakeet"
    
    # 1. Check for explicit symlink (created by install.sh)
    symlink = tools_dir / "model"
    if symlink.is_symlink() or symlink.is_dir():
        return symlink.resolve()
    
    # 2. Check environment variable
    model_version = os.environ.get("PARAKEET_MODEL_VERSION", "").lower()
    if model_version in ("v2", "2"):
        return tools_dir / "model-v2"
    if model_version in ("v3", "3"):
        return tools_dir / "model-v3"
    
    # 3. Check for installed models, prefer v2 (English)
    for version in ["v2", "v3"]:
        model_dir = tools_dir / f"model-{version}"
        if model_dir.is_dir():
            return model_dir
    
    # 4. Fallback to symlink path (will error if not installed)
    return symlink


class ParakeetLazyDaemon:
    def __init__(self):
        self.model_dir = get_model_path()
        self.transcriber = None
        self.last_used = None
        self.running = True
        
        # Validate model exists
        if not self.model_dir.is_dir():
            print(f"Error: Model not found at {self.model_dir}", file=sys.stderr)
            print("Run: ~/.openclaw/extensions/parakeet-stt/scripts/install.sh [v2|v3]", file=sys.stderr)
            sys.exit(1)
        
        print(f"Using model: {self.model_dir}", file=sys.stderr)
        
        # Clean up any existing socket
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            if os.path.exists(SOCKET_PATH):
                raise
        
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)  # world readable/writable
        self.server.listen(1)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        self.running = False

    def ensure_loaded(self):
        if self.transcriber is None:
            print("Loading Parakeet model...", file=sys.stderr)
            self.transcriber = ParakeetTDT(str(self.model_dir))
            print("Model loaded.", file=sys.stderr)
        self.last_used = time.time()

    def unload_if_idle(self):
        if self.transcriber is None or self.last_used is None:
            return
        idle = time.time() - self.last_used
        if idle > IDLE_TIMEOUT:
            print(f"Unloading model (idle {idle:.1f}s)", file=sys.stderr)
            self.transcriber = None
            import gc
            gc.collect()

    def handle_connection(self, conn):
        response = None
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
            if not data:
                response = {"error": "Empty request"}
            else:
                line = data.split(b"\n", 1)[0].strip()
                request = json.loads(line.decode())
                action = request.get("action")
                if action != "transcribe":
                    response = {"error": f"Unsupported action: {action}"}
                else:
                    audio_path = request["audio_path"]
                    self.ensure_loaded()
                    audio = self.transcriber.load_audio(audio_path)
                    text, tokens, timestamps = self.transcriber.transcribe(audio)
                    self.last_used = time.time()
                    response = {"text": text, "tokens": tokens, "timestamps": timestamps}
        except Exception as e:
            response = {"error": str(e)}
        finally:
            if response is not None:
                conn.sendall(json.dumps(response).encode() + b"\n")
            conn.close()
        self.unload_if_idle()

    def run(self):
        print("ParakeetLazyDaemon listening on", SOCKET_PATH, file=sys.stderr)
        while self.running:
            try:
                conn, addr = self.server.accept()
                self.handle_connection(conn)
            except socket.timeout:
                continue
            except Exception as e:
                print("Daemon error:", e, file=sys.stderr)
                continue  # Keep serving instead of breaking
        self.server.close()
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass

if __name__ == "__main__":
    daemon = ParakeetLazyDaemon()
    daemon.run()
