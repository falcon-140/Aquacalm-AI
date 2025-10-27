# services/stt_google.py
from google.cloud import speech_v1p1beta1 as speech
import os
import subprocess
import tempfile


def _has_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return subprocess.run(["which", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _transcode_to_wav(input_path: str) -> str:
    """Transcode input audio to 16k mono WAV using ffmpeg.

    Returns path to the created WAV file. Raises subprocess.CalledProcessError on failure.
    """
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        out_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


def transcribe_audio(file_path: str, language="en-US"):
    """Transcribe an audio file using Google Speech-to-Text.

    If ffmpeg is available and the input is not a WAV/PCM file, we transcode to
    16k mono WAV for reliable recognition. Otherwise we try to call the API
    with the original bytes and let it infer the encoding.
    """
    client = speech.SpeechClient()

    # If not a WAV/PCM file, try to transcode with ffmpeg when available
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    temp_wav = None
    try:
        if ext not in (".wav", ".pcm") and _has_ffmpeg():
            try:
                temp_wav = _transcode_to_wav(file_path)
                use_path = temp_wav
            except Exception:
                # If transcoding fails, fall back to original file
                use_path = file_path
        else:
            use_path = file_path

        with open(use_path, "rb") as f:
            content = f.read()

        audio = speech.RecognitionAudio(content=content)

        # If we transcribed to WAV we supply LINEAR16/16000, otherwise let API infer
        if use_path.endswith(".wav") or use_path.endswith(".pcm"):
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language,
                enable_automatic_punctuation=True,
            )
        else:
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                language_code=language,
                enable_automatic_punctuation=True,
            )

        response = client.recognize(config=config, audio=audio)
        if not response.results:
            return ""
        return " ".join([r.alternatives[0].transcript for r in response.results])
    finally:
        if temp_wav:
            try:
                os.remove(temp_wav)
            except Exception:
                pass
