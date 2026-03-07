#!/usr/bin/env python3
"""Audio recording and OpenAI Whisper transcription."""
import pyaudio
import wave
import io
import threading
import time

RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
MAX_SECS = 10


class Recorder:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.recording = False
        self.frames = []
        self._stream = None
        self._thread = None
        self.error = None
        self.device_index = self._find_input()

    def _find_input(self):
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                return i
        return None

    @property
    def available(self):
        return self.device_index is not None

    def start(self):
        if self.recording:
            return False
        if self.device_index is None:
            self.error = "No audio input device found"
            return False
        self.frames = []
        self.error = None
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
        while self.recording and count < max_frames:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self.frames.append(data)
                count += 1
            except Exception:
                break

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
        return self._to_wav()

    def _to_wav(self):
        if not self.frames:
            return None
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.pa.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(self.frames))
        buf.seek(0)
        return buf

    def close(self):
        if self.recording:
            self.stop()
        self.pa.terminate()


def transcribe(wav_buf, api_key, base_url=None):
    """Transcribe audio using OpenAI Whisper API."""
    if not wav_buf:
        return None, "No audio recorded"
    if not api_key:
        return None, "Whisper API key not set — configure in Setup"
    try:
        import openai
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.OpenAI(**kwargs)
        wav_buf.seek(0)
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", wav_buf, "audio/wav"),
        )
        return result.text, None
    except Exception as e:
        return None, str(e)
