"""
Speech Server — persistent background process, sherpa-onnx Whisper tiny.en.

Model pre-loaded in RAM. 0.24s inference for 3s audio on this CPU.

Protocol (localhost:19848):
  Client sends: RECORD <seconds>\n
  Server sends: OK <text>\n   or   FAIL\n
"""

import sys
import os
import socket
import threading
import warnings

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
warnings.filterwarnings("ignore")

import numpy as np
import sounddevice as sd

PORT = 19848
SAMPLE_RATE = 16000
RECOGNIZER = None


def load_model():
    """Load sherpa-onnx Whisper tiny.en — stays in RAM."""
    global RECOGNIZER
    import sherpa_onnx

    # Model files downloaded by sherpa-onnx
    model_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "Temp", "sherpa-onnx-whisper-tiny.en"
    )

    # If model dir doesn't exist, try to download
    if not os.path.isdir(model_dir):
        # Trigger download via sherpa_onnx utility
        import urllib.request
        import zipfile
        import tempfile
        url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2"
        tmp = os.path.join(tempfile.gettempdir(), "whisper-tiny-en.tar.bz2")
        urllib.request.urlretrieve(url, tmp)
        import tarfile
        with tarfile.open(tmp, "r:bz2") as tar:
            tar.extractall(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"))
        os.unlink(tmp)

    encoder = os.path.join(model_dir, "tiny.en-encoder.int8.onnx")
    decoder = os.path.join(model_dir, "tiny.en-decoder.int8.onnx")
    tokens = os.path.join(model_dir, "tiny.en-tokens.txt")

    RECOGNIZER = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=encoder,
        decoder=decoder,
        tokens=tokens,
        num_threads=4,
        language="en",
        decoding_method="greedy_search",
    )


def record_and_transcribe(duration):
    """Record from mic, transcribe with pre-loaded sherpa-onnx model."""
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype='float32')
    sd.wait()
    audio = audio.flatten()

    # Silence check
    if np.max(np.abs(audio)) < 0.01:
        return None

    # Transcribe — model is already in RAM, ~0.24s for 3s audio
    stream = RECOGNIZER.create_stream()
    stream.accept_waveform(SAMPLE_RATE, audio.tolist())
    RECOGNIZER.decode_stream(stream)
    text = stream.result.text.strip()

    return text if text else None


def handle_client(conn):
    try:
        data = conn.recv(256).decode().strip()
        if data.startswith("RECORD"):
            parts = data.split()
            duration = int(parts[1]) if len(parts) > 1 else 3
            duration = max(1, min(duration, 10))
            text = record_and_transcribe(duration)
            if text:
                conn.sendall(f"OK {text}\n".encode())
            else:
                conn.sendall(b"FAIL\n")
        elif data == "PING":
            conn.sendall(b"PONG\n")
        elif data == "QUIT":
            conn.sendall(b"BYE\n")
            os._exit(0)
    except Exception:
        try:
            conn.sendall(b"FAIL\n")
        except Exception:
            pass
    finally:
        conn.close()


def main():
    load_model()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(1)

    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
