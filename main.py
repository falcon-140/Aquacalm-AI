# main.py
import os
import uuid
import tempfile
import asyncio
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
import shutil
import mimetypes
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables from .env as early as possible so service modules
# that read env vars at import time (e.g., anthropic client) see them.
load_dotenv()

from services.stt_google import transcribe_audio
from services.tts_fish import synthesize_tts
from services.anthropic_client import send_to_claude
from services.convo_memory import ConversationStore
from services.voice_clone import ensure_voice_profile, clone_voice_if_needed
from fastapi import WebSocket, WebSocketDisconnect

load_dotenv()
PORT = int(os.getenv("PORT", 8787))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ensure tts cache directory exists
os.makedirs("tts_cache", exist_ok=True)

db = ConversationStore("sqlite:///convo_memory.db")

@app.post("/session/new")
async def new_session(user_name: str = Form(...)):
    session_id = str(uuid.uuid4())
    db.create_session(session_id, user_name)
    return {"session_id": session_id}

@app.post("/audio/turn")
async def audio_turn(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    voice_profile: str = Form(None)  # optional voice profile id
):
    # save uploaded file to temp
    suffix = os.path.splitext(audio.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    # Attempt STT on the uploaded file so the frontend can show a transcript.
    transcript = ""
    try:
        transcript = transcribe_audio(tmp_path, language=os.getenv("SPEECH_LANGUAGE", "en-US"))
    except Exception as e:
        # don't fail the request; log and continue to return the audio back
        print("STT error:", e)

    # Move the uploaded audio into tts_cache and return its URL.
    dest_name = f"{uuid.uuid4()}{suffix}"
    dest_path = os.path.join("tts_cache", dest_name)
    try:
        shutil.move(tmp_path, dest_path)
    except Exception:
        # fallback to copy if move fails
        shutil.copy(tmp_path, dest_path)

    # If we have a transcript, try to produce an LLM-based assistant reply via Anthropic.
    assistant_text = ""
    if transcript:
        try:
            # send_to_claude is async; we call it and await its result
            claude_resp = await send_to_claude(transcript, system_prompt=db.system_prompt())
            assistant_text = claude_resp or f"I heard: '{transcript}'. How can I help you further?"
        except Exception as e:
            # on any LLM error, fall back to a local empathetic reply
            print("Anthropic error:", e)
            assistant_text = f"I heard: '{transcript}'. How can I help you further?"
    else:
        assistant_text = "(no assistant response)"

    # Generate TTS for the assistant's response
    try:
        tts_path = synthesize_tts(assistant_text)
        tts_filename = os.path.basename(tts_path)
    except Exception as e:
        print("TTS error:", e)
        tts_filename = dest_name  # fallback to original audio if TTS fails

    return {
        "transcript": transcript,
        "assistant_text": assistant_text,
        "tts_url": f"/audio/tts/{tts_filename}"
    }

@app.get("/audio/tts/{filename}")
def get_tts(filename: str):
    path = os.path.join("tts_cache", filename)
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    mime, _ = mimetypes.guess_type(path)
    media_type = mime or "application/octet-stream"
    return FileResponse(path, media_type=media_type)

@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.websocket("/ws/llm")
async def websocket_llm(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            # expect {"transcript": "..."}
            transcript = msg.get("transcript")
            if not transcript:
                await ws.send_json({"error": "no_transcript"})
                continue

            # call the LLM and stream the response back in chunks
            try:
                claude_resp = await send_to_claude(transcript, system_prompt=db.system_prompt())
                if not claude_resp:
                    claude_resp = "(empty response)"
            except Exception as e:
                await ws.send_json({"error": "llm_error", "detail": str(e)})
                continue

            # stream the response in small chunks to simulate realtime
            chunk_size = 120
            for i in range(0, len(claude_resp), chunk_size):
                chunk = claude_resp[i:i+chunk_size]
                await ws.send_json({"chunk": chunk})

            # Generate TTS for the complete response
            try:
                tts_path = synthesize_tts(claude_resp)
                tts_filename = os.path.basename(tts_path)
                await ws.send_json({
                    "done": True,
                    "tts_url": f"/audio/tts/{tts_filename}"
                })
            except Exception as e:
                print("TTS error:", e)
                await ws.send_json({"done": True})
    except WebSocketDisconnect:
        return
@app.post("/text/turn")
async def text_turn(payload: dict):
    user_text = payload.get("text", "")
    if not user_text:
        return {"reply": "(no input text)"}

    try:
        claude_resp = await send_to_claude(user_text, system_prompt=db.system_prompt())
        reply_text = claude_resp or "(empty response)"
    except Exception as e:
        print("LLM error:", e)
        reply_text = f"I heard: '{user_text}'. How can I help you further?"

    try:
        tts_path = synthesize_tts(reply_text)
        tts_filename = os.path.basename(tts_path)
        return {
            "reply": reply_text,
            "tts_url": f"/audio/tts/{tts_filename}"
        }
    except Exception as e:
        print("TTS error:", e)
        return {"reply": reply_text}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
