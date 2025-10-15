from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
    connector = aiohttp.TCPConnector(limit=64, keepalive_timeout=30)
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20),
        connector=connector
    )

@app.on_event("shutdown")
async def _shutdown():
    global session
    if session:
        await session.close()
        session = None

def _authed(req: Request) -> bool:
    return (not TTS_SHARED_TOKEN) or (req.headers.get("X-TTS-Token") == TTS_SHARED_TOKEN)

def _accept_for(fmt: str) -> str:
    """Map format string to appropriate Accept header for ElevenLabs"""
    fmt = (fmt or "").lower()
    if "ogg" in fmt or "opus" in fmt:
        return "audio/ogg"
    return "audio/mpeg"

async def eleven_stream(text: str, voice_id: str = None, model_id: str = None, 
                        voice_settings: dict = None, optimize_latency: int = 4,
                        accept: str = "audio/mpeg"):
    """Stream audio from ElevenLabs with configurable parameters"""
    assert session is not None, "Session not initialized"
    
    # Use defaults if not specified
    voice_id = voice_id or ELEVEN_VOICE_ID
    model_id = model_id or "eleven_flash_v2_5"
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Accept": accept,  # Dynamic based on requested format
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

@app.post("/tts/speech")
async def owui_backend_compat(request: Request):
    """Open Web UI backend-compatible endpoint (server-to-server)"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Open WebUI can send: {"text": "..."} or {"input": "..."}
    text = payload.get("text") or payload.get("input") or ""
    text = text.strip()
    
    # Voice ID (optional, use default if not provided)
    voice = payload.get("voice") or payload.get("voice_id") or ELEVEN_VOICE_ID
    
    # Handle "Default" voice name by falling back to env voice
    if voice and voice.lower() == "default":
        voice = ELEVEN_VOICE_ID
    
    # Format (optional, we default to MP3)
    fmt = payload.get("format") or "audio/mpeg"
    
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' or 'input' field")
    
    # Get proper Accept header and media type for requested format
    accept = _accept_for(fmt)
    
    # Use our optimized Flash 2.5 pipeline
    return StreamingResponse(
        eleven_stream(text=text, voice_id=voice, model_id="eleven_flash_v2_5", 
                     optimize_latency=4, accept=accept),
        media_type=accept,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"}
    )

@app.post("/tts//speech")
async def owui_backend_compat_slashslash(request: Request):
    """Alias for double-slash (handles trailing slash in TTS_API_BASE_URL)"""
    return await owui_backend_compat(request)

@app.post("/v1/text-to-speech/{voice_id}")
async def eleven_compatible(voice_id: str, request: Request):
    """ElevenLabs-compatible endpoint for Open Web UI (versioned)"""
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
        media_type="audio/mpeg",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"}
    )

@app.post("/text-to-speech/{voice_id}")
async def eleven_compatible_alias(voice_id: str, request: Request):
    """ElevenLabs-compatible endpoint alias (non-versioned path)"""
    return await eleven_compatible(voice_id, request)

# OpenAI-compatible TTS endpoint
class OpenAITTSRequest(BaseModel):
    model: str = "tts-1"
    voice: str | None = None
    input: str
    response_format: str | None = "mp3"
    speed: float | None = 1.0

def _mime_type(fmt: str) -> str:
    """Map response format to MIME type"""
    return {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "wav": "audio/wav",
        "aac": "audio/aac",
        "flac": "audio/flac",
    }.get((fmt or "mp3").lower(), "audio/mpeg")

@app.post("/v1/audio/speech")
async def openai_audio_speech(req: OpenAITTSRequest, request: Request):
    """OpenAI-compatible TTS endpoint for Open Web UI"""
    # Optional shared token check for server-to-server calls
    if TTS_SHARED_TOKEN:
        given = request.headers.get("X-TTS-Token", "")
        if given != TTS_SHARED_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid TTS token")
    
    text = req.input.strip()
    voice = req.voice or ELEVEN_VOICE_ID
    
    # Handle "Default" voice name by falling back to env voice
    if voice and voice.lower() == "default":
        voice = ELEVEN_VOICE_ID
    
    fmt = (req.response_format or "mp3").lower()
    speed = req.speed or 1.0
    
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'input' text")
    
    if not voice:
        raise HTTPException(status_code=400, detail="Missing voice ID")
    
    # Get proper Accept header and media type for requested format
    accept = _mime_type(fmt)
    
    # Use our optimized Flash 2.5 pipeline
    return StreamingResponse(
        eleven_stream(
            text=text,
            voice_id=voice,
            model_id="eleven_flash_v2_5",
            optimize_latency=4,
            accept=accept
        ),
        media_type=accept,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"}
    )
