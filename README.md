# 🎙️ Voice Bot - Real-Time Conversational AI

A production-ready voice bot with intelligent interruption handling, powered by Groq (ultra-fast LLM), Deepgram (high-accuracy STT), and Silero VAD (client-side speech detection).

## ✨ Features

- ⚡ **Ultra-Fast Responses**: Groq Llama-3.3-70B delivers 500+ tokens/second
- 🎤 **Smart Interruptions**: Natural barge-in handling with pause-and-decide strategy
- 🧠 **Context-Aware**: Maintains conversation history with intelligent prompt management
- 🔊 **High-Quality STT**: Deepgram Nova-2 for accurate transcription
- 🌐 **Client-Side VAD**: Silero neural network for instant speech detection
- 🔄 **Stateful & Concurrent**: Handles multiple users, each with isolated state
- 📝 **Clean Architecture**: Modular design with clear separation of concerns

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- macOS, Linux, or Windows
- Microphone-enabled device
- Internet connection (for API services)

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd voice_bot
```

### 2. Set Up Environment Variables

Create a `.env` file in the root directory:

```bash
# Deepgram API Key (for Speech-to-Text)
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# Groq API Key (for LLM)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

**Get Your API Keys**:
- **Deepgram**: Sign up at https://console.deepgram.com/
- **Groq**: Sign up at https://console.groq.com/keys (free tier available!)

### 3. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Run the Application

**Option A: Start Both Server and Client (Recommended)**

```bash
bash start_both.sh
```

This will:
- Start the server on `http://127.0.0.1:8000`
- Start the client on `http://localhost:3000`
- Open the client automatically in your browser

**Option B: Start Separately**

Terminal 1 - Server:
```bash
source venv/bin/activate
python server.py
```

Terminal 2 - Client:
```bash
cd client_app
python3 run_client.py
```

Then open: http://localhost:3000

### 5. Use the Voice Bot

1. Click **"Connect"** to establish WebSocket connection
2. Click **"Start Listening"** to activate Silero VAD
3. **Speak naturally** - the AI will detect when you start and stop
4. **Interrupt anytime** - the system handles barge-ins gracefully
5. Click **"Stop Listening"** when done

## 📁 Project Structure

```
voice_bot/
├── server.py                    # FastAPI server entry point
├── requirements.txt             # Python dependencies
├── .env                         # API keys (create this!)
├── start_both.sh               # Start server + client script
│
├── src/
│   └── server/                 # Server-side modules
│       ├── orchestrator.py         # Main orchestrator
│       ├── stt.py              # Speech-to-Text (Deepgram)
│       ├── ai_agent.py         # AI Agent (Groq + LangGraph)
│       ├── tts.py              # Text-to-Speech (gTTS)
│       ├── prompt_generator.py # Prompt construction logic
│       ├── interruption_handler.py  # Interruption management
│       ├── audio_playback.py   # Playback state tracking
│       └── state_types.py      # Status enums
│
├── client_app/                 # Client-side application
│   ├── index.html              # Main HTML page
│   ├── run_client.py           # Client HTTP server
│   ├── styles.css              # Styling
│   ├── app.js                  # Main application logic
│   ├── silero_vad.js           # Silero VAD integration
│   ├── websocket_client.js     # WebSocket communication
│   ├── ui_manager.js           # UI updates
│   └── logger.js               # Client-side logging
│
└── docs/
    ├── ARCHITECTURE.md         # System architecture
    ├── TECHNICAL_GUIDE.md      # Detailed technical documentation
    └── README.md               # This file
```

## 🔧 Configuration

### Environment Variables

All API keys and configuration are in `.env`:

```bash
# Required
DEEPGRAM_API_KEY=<your_key>    # Deepgram Speech-to-Text
GROQ_API_KEY=<your_key>        # Groq LLM

# Optional (with defaults)
GROQ_MODEL=llama-3.3-70b-versatile  # Groq model to use
```

### Server Configuration

Edit `server.py` to change server settings:

```python
# Default: localhost:8000
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="127.0.0.1",  # Change to 0.0.0.0 for network access
        port=8000,         # Change port if needed
        reload=False       # Set True for auto-reload during development
    )
```

### Client Configuration

Edit `client_app/websocket_client.js` to change WebSocket URL:

```javascript
// Default: ws://127.0.0.1:8000/ws
this.url = url || 'ws://127.0.0.1:8000/ws';
```

## 🎯 How It Works

### High-Level Flow

```
1. User speaks → Silero VAD detects speech start
2. Client records audio → Sends to server when speech ends
3. Server transcribes (Deepgram) → Sends text to LLM
4. LLM generates response (Groq) → Streams text to TTS
5. TTS converts to audio (gTTS) → Sends to client
6. Client plays audio → User hears response
```

### Interruption Handling

```
User interrupts mid-response:
├─ Client: Stop audio immediately
├─ Server: Clear audio/text queues
├─ Server: Transcribe user's new speech
└─ Server: Decide:
    ├─ False alarm ("uh-huh") → Resume playback
    └─ Real interruption → Clean history & regenerate
```

### Chat History Management

When interrupted, the system intelligently manages conversation history:

**Before**:
```
[1] USER: "How are you doing?"
[2] AGENT: "I'm doing well, thank you..." [INTERRUPTED]
```

**User says**: "What are you doing by the way?"

**After**:
```
[1] USER: "How are you doing? What are you doing by the way?"
```

The unheard agent response is removed, and the new text is appended to create a natural, combined question.

## 🐛 Troubleshooting

### "Address already in use" Error

```bash
# Kill processes on ports 8000 and 3000
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9

# Or use the restart script
bash restart.sh
```

### Microphone Not Working

1. Check browser permissions (allow microphone access)
2. Ensure HTTPS or localhost (browsers require secure context for mic)
3. Try a different browser (Chrome/Edge recommended)

### STT Not Detecting Speech

1. Check Deepgram API key in `.env`
2. Check audio format compatibility (should be WebM or WAV)
3. Check server logs for Deepgram errors
4. Try speaking louder or closer to microphone

### LLM Taking Too Long / Rate Limited

1. Check Groq API key in `.env`
2. Groq free tier has rate limits (50 requests/day)
3. Check server logs for 429 errors
4. Wait a few minutes and try again

### Audio Not Playing

1. Check browser console for errors
2. Ensure gTTS is installed: `pip install gTTS`
3. Check server logs for TTS errors
4. Try refreshing the page

## 🧪 Development

### Running in Development Mode

```bash
# Server with auto-reload
python server.py --reload

# Client (already auto-serves static files)
cd client_app && python3 run_client.py
```

### Testing

```bash
# Test server health
curl http://127.0.0.1:8000/health

# Expected response:
{
  "status": "healthy",
  "deepgram_configured": true,
  "groq_configured": true,
  "groq_model": "llama-3.3-70b-versatile",
  "performance": "⚡ Ultra-fast with Groq (500+ tokens/sec)"
}
```

## 📊 Performance

### Typical Latency

| Component | Latency |
|-----------|---------|
| VAD Detection (client) | 10-50ms |
| STT (Deepgram) | 200-500ms |
| LLM First Token (Groq) | 100-300ms |
| LLM Streaming (Groq) | 500+ tokens/sec |
| TTS (gTTS) | 300-800ms per sentence |

### Bottlenecks & Solutions

**Problem**: TTS (gTTS) is synchronous and slow

**Current Solution**: Run in thread pool executor

**Future**: Switch to faster TTS:
- ElevenLabs (100-200ms, high quality)
- Deepgram Aura (50-100ms, ultra-fast)
- Coqui TTS (on-device, free)


## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Groq**: Ultra-fast LLM inference
- **Deepgram**: High-quality speech-to-text
- **Silero**: Client-side VAD model
- **FastAPI**: Modern Python web framework
- **LangChain/LangGraph**: LLM orchestration
