from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import aiohttp, os, json

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "")
TTS_SHARED_TOKEN = os.getenv("TTS_SHARED_TOKEN", "")  # optional shared secret

app = FastAPI()

def _authed(req: Request) -> bool:
    return (not TTS_SHARED_TOKEN) or (req.headers.get("X-TTS-Token") == TTS_SHARED_TOKEN)

async def eleven_stream(text: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}/stream"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Accept": "audio/ogg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "optimize_streaming_latency": 3,  # tune 0..4 for TTFA
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.post(url, json=payload, headers=headers) as r:
            r.raise_for_status()
            async for chunk in r.content.iter_chunked(8192):
                if chunk:
                    yield chunk

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.post("/speak")
async def speak(req: Request):
    if not _authed(req): raise HTTPException(status_code=401, detail="Unauthorized")
    data = await req.json()
    text = data.get("text", "").strip()
    if not text: raise HTTPException(status_code=400, detail="Empty text")
    return StreamingResponse(eleven_stream(text), media_type="audio/ogg")
