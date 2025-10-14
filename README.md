# Aurora TTS Microservice

High-performance, low-latency Text-to-Speech microservice using ElevenLabs API with streaming audio support.

## Features

- 🚀 **Streaming Audio**: Real-time audio streaming for minimal latency
- 🔐 **Secure**: Token-based authentication
- 🎯 **Optimized**: Tuned for ChatGPT-like conversation performance
- 📡 **API Compatible**: Works seamlessly with OpenWebUI

## Quick Deploy on Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Manual Deployment

1. **Create New Web Service** on Render
2. **Connect this repository**
3. **Configure**:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn tts_proxy:app --host 0.0.0.0 --port $PORT`
4. **Set Environment Variables**:
   ```
   ELEVEN_API_KEY=your_elevenlabs_api_key
   ELEVEN_VOICE_ID=your_voice_id
   TTS_SHARED_TOKEN=random_secure_token
   ```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ELEVEN_API_KEY` | ✅ | Your ElevenLabs API key |
| `ELEVEN_VOICE_ID` | ✅ | Default voice ID from ElevenLabs |
| `TTS_SHARED_TOKEN` | 🔒 | Shared secret for authentication (recommended) |

## API Endpoints

### Health Check
```bash
GET /healthz
```
Returns: `{"ok": true}`

### Text-to-Speech
```bash
POST /speak
Content-Type: application/json
X-TTS-Token: your_shared_token

{
  "text": "Hello, this is a test message"
}
```
Returns: Streaming `audio/ogg` response

## Integration with OpenWebUI Proxy

This service is designed to work with the Aurora WebUI Proxy. Configure your proxy with:

```bash
TTS_PROXY_ORIGIN=https://your-tts-service.onrender.com
TTS_SHARED_TOKEN=same_token_as_this_service
```

## Performance Tuning

### ElevenLabs Optimization
- `optimize_streaming_latency`: Set to 3-4 for fastest response
- Use appropriate voice models (multilingual vs English-only)

### Render Optimization
- Enable "Always On" to prevent cold starts
- Deploy in same region as your main application
- Use paid plan for better performance

## Security

- Always set `TTS_SHARED_TOKEN` in production
- Keep `ELEVEN_API_KEY` secure
- Monitor ElevenLabs usage to prevent quota exhaustion

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ELEVEN_API_KEY=your_key
export ELEVEN_VOICE_ID=your_voice_id
export TTS_SHARED_TOKEN=dev_token

# Run locally
uvicorn tts_proxy:app --host 0.0.0.0 --port 8000 --reload
```

Test: `curl -X POST http://localhost:8000/speak -H "Content-Type: application/json" -H "X-TTS-Token: dev_token" -d '{"text": "Hello world"}' --output test.ogg`
