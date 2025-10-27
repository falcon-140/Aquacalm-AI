# services/tts_fish.py
import os
import time
import requests
import pathlib
import uuid

FISH_API_KEY = os.getenv("FISH_API_KEY", "cdb035ad393f421987df4879369b9b7f")
FISH_API_ROOT = "https://api.fish.audio/v1/tts"  # Correct endpoint

def synthesize_tts(text: str, voice_id=None, format="mp3"):
    if voice_id is None:
        voice_id = os.getenv("FISH_VOICE_ID")

    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "model": os.getenv("FISH_TTS_MODEL", "speech-1.6"),
    }

    try:
        # Call the Fish Audio API
        resp = requests.post(FISH_API_ROOT, headers=headers, json=payload)

        # 402 means invalid key or no credits
        if resp.status_code == 402:
            raise Exception("Fish API key invalid or credits exhausted.")

        # 200 means we got audio data (binary)
        if resp.status_code != 200:
            raise Exception(f"Bad response {resp.status_code}: {resp.text}")

        # Save the binary MP3/WAV data
        out_dir = pathlib.Path("tts_cache")
        out_dir.mkdir(exist_ok=True)
        filename = f"tts_{uuid.uuid4()}.{format}"
        path = out_dir / filename

        path.write_bytes(resp.content)
        return str(path)

    except Exception as e:
        print("TTS error:", e)
        return None
