from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import aiohttp, os, json

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "")
TTS_SHARED_TOKEN = os.getenv("TTS_SHARED_TOKEN", "")  # optional shared secret

app = FastAPI()

# Global session for connection reuse (avoids TLS handshake on every request)
session: aiohttp.ClientSession | None = None

@app.on_event("startup")
async def _startup():
    global session
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))

@app.on_event("shutdown")
async def _shutdown():
    global session
    if session:
        await session.close()
        session = None

def _authed(req: Request) -> bool:
    return (not TTS_SHARED_TOKEN) or (req.headers.get("X-TTS-Token") == TTS_SHARED_TOKEN)

async def eleven_stream(text: str, voice_id: str = None, model_id: str = None, 
                        voice_settings: dict = None, optimize_latency: int = 4):
    """Stream audio from ElevenLabs with configurable parameters"""
    assert session is not None, "Session not initialized"
    
    # Use defaults if not specified
    voice_id = voice_id or ELEVEN_VOICE_ID
    model_id = model_id or "eleven_flash_v2_5"
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Accept": "audio/mpeg",  # MP3 for better compatibility
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "optimize_streaming_latency": optimize_latency,
    }
    
    # Add voice_settings if provided
    if voice_settings:
        payload["voice_settings"] = voice_settings
    
    async with session.post(url, json=payload, headers=headers) as r:
        if r.status != 200:
            error_text = await r.text()
            raise HTTPException(status_code=502, detail=f"ElevenLabs API error: {error_text}")
        
        async for chunk in r.content.iter_chunked(8192):
            if chunk:
                yield chunk

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.post("/speak")
async def speak(req: Request):
    """Legacy endpoint with token auth"""
    if not _authed(req): raise HTTPException(status_code=401, detail="Unauthorized")
    data = await req.json()
    text = data.get("text", "").strip()
    if not text: raise HTTPException(status_code=400, detail="Empty text")
    return StreamingResponse(eleven_stream(text), media_type="audio/mpeg")

@app.post("/v1/text-to-speech/{voice_id}")
async def eleven_compatible(voice_id: str, request: Request):
    """ElevenLabs-compatible endpoint for Open Web UI"""
    body = await request.json()
    text = body.get("text", "").strip()
    
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    
    # Extract optional parameters
    model_id = body.get("model_id", "eleven_flash_v2_5")
    voice_settings = body.get("voice_settings")
    optimize_latency = body.get("optimize_streaming_latency", 4)
    
    return StreamingResponse(
        eleven_stream(text, voice_id, model_id, voice_settings, optimize_latency),
        media_type="audio/mpeg"
    )
