#!/usr/bin/env python3
"""
Local speech recognition using Vosk (offline, no API key needed).
Model: vosk-model-small-en-us-0.15  (~40MB, stored in ./model/)
Falls back gracefully if model not loaded yet.
"""
import pyaudio
import wave
import io
import json
import threading
import os

RATE     = 16000
CHANNELS = 1
FORMAT   = pyaudio.paInt16
CHUNK    = 4000   # Vosk prefers larger chunks
MAX_SECS = 10

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")

# Load Vosk model once at import time (non-blocking — done in background thread)
_model      = None
_model_lock = threading.Lock()
_model_ready = threading.Event()

def _load_model():
    global _model
    try:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)   # suppress verbose output
        with _model_lock:
            _model = Model(MODEL_PATH)
        _model_ready.set()
        print("Vosk model loaded")
    except Exception as e:
        print(f"Vosk model load error: {e}")
        _model_ready.set()   # unblock waiter even on failure

# Start loading immediately when app starts
threading.Thread(target=_load_model, daemon=True).start()


class Recorder:
    def __init__(self):
        self.pa           = pyaudio.PyAudio()
        self.recording    = False
        self.frames       = []
        self._stream      = None
        self._thread      = None
        self.error        = None
        self.device_index = self._find_input()
        self._last_level  = 0

    def _find_input(self):
        for i in range(self.pa.get_device_count()):
            if self.pa.get_device_info_by_index(i)['maxInputChannels'] > 0:
                return i
        return None

    @property
    def available(self):
        return self.device_index is not None

    @property
    def model_ready(self):
        return _model_ready.is_set() and _model is not None

    def start(self):
        if self.recording:
            return False
        if self.device_index is None:
            self.error = "No audio input device found"
            return False
        self.frames = []
        self.error  = None
        try:
            self._stream = self.pa.open(
                format=FORMAT, channels=CHANNELS, rate=RATE,
                input=True, input_device_index=self.device_index,
                frames_per_buffer=CHUNK
            )
            self.recording = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def _loop(self):
        max_frames = int(RATE / CHUNK * MAX_SECS)
        count = 0
        import numpy as np
        while self.recording and count < max_frames:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self.frames.append(data)
                # Calculate level
                a = np.frombuffer(data, dtype=np.int16)
                self._last_level = np.sqrt(np.mean(a.astype(np.float32)**2)) if len(a) > 0 else 0
                count += 1
            except Exception:
                break
        self._last_level = 0

    @property
    def level(self):
        """Current RMS level (0-32768 approx)"""
        return self._last_level

    def stop(self):
        self.recording = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        return b''.join(self.frames)

    def close(self):
        if self.recording:
            self.stop()
        self.pa.terminate()


def transcribe(audio_bytes):
    """
    Transcribe raw PCM bytes (16kHz, mono, s16le) using local Vosk model.
    Returns (text, error_string).
    """
    if not audio_bytes:
        return None, "No audio recorded"

    with _model_lock:
        model = _model

    if model is None:
        if not _model_ready.is_set():
            return None, "Model still loading, try again"
        return None, f"Model not found — check {MODEL_PATH}"

    try:
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(model, RATE)
        rec.SetWords(False)

        # Feed audio in chunks
        chunk_size = CHUNK * 2   # bytes
        for i in range(0, len(audio_bytes), chunk_size):
            rec.AcceptWaveform(audio_bytes[i:i + chunk_size])

        result = json.loads(rec.FinalResult())
        text   = result.get("text", "").strip()
        return (text or None), (None if text else "Nothing recognized")
    except Exception as e:
        return None, str(e)
