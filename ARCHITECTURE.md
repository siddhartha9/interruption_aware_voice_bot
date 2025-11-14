# Voice Bot Architecture

# https://docs.google.com/document/d/1cYYcNCvQsT9oi_l4qJ9fuSXnLt11JXyiPTQ_8J0Gf14/edit?usp=sharing

## System Overview

This is a **real-time, stateful, concurrent voice bot** with intelligent interruption handling. The system uses a client-server architecture where the client handles voice activity detection (VAD) and the server orchestrates speech-to-text (STT), AI agent (LLM), and text-to-speech (TTS).

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Silero VAD   │  │ Audio Input  │  │ Audio Output │         │
│  │ (Speech      │  │ (Microphone) │  │ (Speakers)   │         │
│  │  Detection)  │  └──────────────┘  └──────────────┘         │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
                           ↕ WebSocket
┌─────────────────────────────────────────────────────────────────┐
│                      SERVER (Python/FastAPI)                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              CONNECTION ORCHESTRATOR                     │  │
│  │         (State Management & Workflow Control)            │  │
│  └─────────────────────────────────────────────────────────┘  │
│          │          │          │          │          │         │
│     ┌────▼────┐ ┌──▼──┐ ┌────▼────┐ ┌───▼───┐ ┌────▼────┐   │
│     │   STT   │ │ LLM │ │   TTS   │ │Prompt │ │Interrupt│   │
│     │(Deepgram│ │(Groq│ │ (gTTS)  │ │  Gen  │ │ Handler │   │
│     │ Nova-2) │ │Llama│ │         │ │       │ │         │   │
│     └─────────┘ └─────┘ └─────────┘ └───────┘ └─────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Architecture Approach: VAD on Client (Recommended)

We use **client-side VAD** with server-side orchestration for optimal performance:

### Why Client-Side VAD?
- ✅ **Lower Latency**: No round-trip to server for voice detection
- ✅ **Reduced Bandwidth**: Only send audio when speech detected
- ✅ **Better UX**: Immediate visual feedback to user
- ✅ **Privacy**: Audio not sent until user speaks

### Components

#### Client-Side (JavaScript)
1. **Silero VAD**: Neural network-based voice activity detection
2. **MediaRecorder**: Captures audio when speech detected
3. **WebSocket Client**: Sends/receives events and audio data
4. **Audio Playback**: Sequential audio queue for agent responses

#### Server-Side (Python)
1. **Connection Orchestrator**: Main state machine and workflow controller
2. **STT Processor**: Deepgram Nova-2 for speech-to-text
3. **AI Agent**: Groq Llama-3.3-70B for ultra-fast LLM responses
4. **TTS Module**: Google TTS (gTTS) for text-to-speech
5. **Prompt Generator**: Intelligent prompt construction and history management
6. **Interruption Handler**: Manages pause-and-decide interruption strategy

## Key Design Patterns

### 1. Stateful Orchestration
The `ConnectionOrchestrator` maintains state for each WebSocket connection:

```python
class ConnectionOrchestrator:
    # State Variables
    stt_status: Status           # IDLE | PROCESSING
    agent_status: Status         # IDLE | PROCESSING | STREAMING
    tts_status: Status           # IDLE | PROCESSING
    playback_status: Status      # IDLE | ACTIVE | PAUSED
    interruption_status: InterruptionStatus  # IDLE | PROCESSING | ACTIVE
    
    # Data Queues
    stt_job_queue: asyncio.Queue       # Audio buffers to transcribe
    stt_output_list: List[str]         # Completed transcriptions
    text_stream_queue: asyncio.Queue   # Agent → TTS
    audio_output_queue: AudioOutputQueue  # TTS → Client
    chat_history: List[Dict]            # Conversation history
```

### 2. Event-Driven Architecture

**Client Events**:
- `speech_start`: User started speaking (detected by Silero VAD)
- `speech_end`: User stopped speaking (includes audio buffer)
- `client_playback_started`: Client started playing audio
- `client_playback_complete`: Client finished playing all audio

**Server Events**:
- `connected`: Connection established
- `stop_playback`: Interrupt client audio immediately
- `play_audio`: Audio chunk for client to play
- `error`: Error message

### 3. Asynchronous Workers

**Background Tasks**:
```python
# STT Worker: Processes audio buffers continuously
async def stt_worker():
    while True:
        audio_buffer = await stt_job_queue.get()
        text = await stt_processor.transcribe_audio(audio_buffer)
        stt_output_list.append(text)
        llm_task.trigger()

# TTS Worker: Converts text to audio continuously
async def tts_worker():
    while True:
        text = await text_stream_queue.get()
        audio = await text_to_speech(text)
        await audio_output_queue.put(audio)

# Playback Worker: Server-side playback state tracking
async def playback_worker():
    # Tracks when audio is sent to client
    # Auto-manages IDLE ↔ ACTIVE transitions
```

### 4. Queue-Based Decoupling

**Advantages**:
- ✅ Components don't block each other
- ✅ Natural buffering and flow control
- ✅ Easy to cancel/clear during interruptions
- ✅ Supports concurrent operations

```
User Audio → [stt_job_queue] → STT Worker → [stt_output_list] → Prompt Gen
                                                                       ↓
Client ← [audio_output_queue] ← TTS Worker ← [text_stream_queue] ← Agent
```

## Interruption Handling (Pause-and-Decide Strategy)

### The Challenge
When a user speaks while the agent is responding, the system must:
1. Stop agent audio immediately
2. Listen to the user
3. Decide: Resume or regenerate?

### The Solution

#### Step 1: User Starts Speaking (Event 1)
```python
async def on_user_starts_speaking():
    # Check if system is busy
    if not is_system_idle():
        # TRUE INTERRUPTION
        interruption_status = ACTIVE
        
        # Send stop signal to client
        websocket.send({"event": "stop_playback"})
        
        # Clear queues (audio + text)
        audio_output_queue.clear()
        text_stream_queue.clear()
        
        # Cancel agent if still PROCESSING (not STREAMING)
        if agent_status == PROCESSING:
            ai_agent.cancel()
```

#### Step 2: User Ends Speaking (Event 2)
```python
async def on_user_ends_speaking(audio_buffer):
    # Add to STT queue
    stt_job_queue.put(audio_buffer)
    # STT worker will process and trigger LLM task
```

#### Step 3: LLM Processing Task (The Decision Maker)
```python
async def llm_processing_task():
    # 1. Merge ALL STT outputs
    # 2. Check if false alarm (backchannel like "uh-huh")
    # 3. Decide: Resume or Regenerate?
    
    is_new_prompt_needed, user_prompt, cleaned_history = \
        prompt_generator.generate_prompt(
            stt_output_list,
            chat_history,
            is_interruption=True
        )
    
    if not is_new_prompt_needed:
        # FALSE ALARM - Resume playback
        websocket.send({"event": "playback_resume"})
        playback_status = ACTIVE
    else:
        # TRUE INTERRUPTION - Regenerate
        # cleaned_history has unheard agent response removed
        # and new user text appended to previous message
        chat_history = cleaned_history
        
        # Call agent with cleaned history
        await run_agent_flow(chat_history)
```

### Chat History Management During Interruption

**Problem**: When interrupted, the agent's partial response was never heard by the user.

**Solution**: The `PromptGenerator` cleans the history:

1. **Remove unheard agent response**
2. **Append new user text to previous user message**

**Example**:
```
BEFORE INTERRUPTION:
[1] USER: "How are you doing?"
[2] AGENT: "I'm doing well, thank you for..." [INTERRUPTED]

USER INTERRUPTS: "What are you doing by the way?"

AFTER CLEANUP:
[1] USER: "How are you doing? What are you doing by the way?"
```

This creates a natural, combined question for the LLM.

## Technology Stack

### Client
- **HTML5/JavaScript**: Core client application
- **Silero VAD**: Neural network voice activity detection (ONNX model)
- **MediaRecorder API**: Audio capture
- **WebSocket API**: Real-time communication

### Server
- **Python 3.9+**: Core language
- **FastAPI**: Web framework with WebSocket support
- **Uvicorn**: ASGI server
- **asyncio**: Async/await concurrency

### AI Services
- **Deepgram Nova-2**: Speech-to-text (cloud API)
- **Groq Llama-3.3-70B**: LLM inference (500+ tokens/sec)
- **gTTS**: Text-to-speech (free Google TTS)

### Key Libraries
- **langchain**: LLM framework
- **langchain-groq**: Groq integration
- **langgraph**: Stateful LLM workflows
- **deepgram-sdk**: Deepgram API client
- **python-dotenv**: Environment variable management

## Concurrency & State Management

### Status Enums
```python
class Status(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    STREAMING = "streaming"
    ACTIVE = "active"
    PAUSED = "paused"

class InterruptionStatus(Enum):
    IDLE = "idle"
    PROCESSING = "processing"  # Lock during interrupt check
    ACTIVE = "active"           # Confirmed interruption
```

### System Idle Check
```python
def is_system_idle():
    return (
        stt_status == IDLE and
        agent_status == IDLE and
        tts_status == IDLE and
        playback_status == IDLE and
        not client_playback_active and
        not response_in_progress
    )
```

### Response Tracking
```python
# Tracks entire response cycle
response_in_progress = True  # Set when agent starts
# ...agent generates, TTS processes, client plays...
response_in_progress = False  # Set when client finishes playing

# This ensures interruptions during any phase are detected
```

## Scalability Considerations

### Current Design (Single Instance)
- ✅ Each WebSocket connection gets isolated `ConnectionOrchestrator`
- ✅ No shared state between connections
- ✅ FastAPI handles multiple concurrent connections

### For Production Scale
Consider:
1. **Load Balancer**: Distribute WebSocket connections
2. **Redis**: Share state across multiple server instances
3. **Message Queue**: Decouple STT/LLM/TTS into separate services
4. **Database**: Persist conversation history
5. **Monitoring**: Track latency, errors, token usage

## Performance Characteristics

### Latency Breakdown (Typical)
- **VAD Detection**: 10-50ms (client-side, near-instant)
- **WebSocket RTT**: 5-20ms (local network)
- **STT (Deepgram)**: 200-500ms (network + processing)
- **LLM (Groq)**: 100-300ms for first token, then 500+ tokens/sec streaming
- **TTS (gTTS)**: 300-800ms per sentence (blocking, run in thread pool)
- **Audio Playback**: Real-time (depends on audio length)

### Bottlenecks
1. **TTS (gTTS)**: Synchronous HTTP calls, 500-2000ms per call
   - Mitigation: Run in thread pool executor
   - Future: Switch to faster TTS (ElevenLabs, Deepgram Aura)
2. **Network Latency**: STT and LLM are cloud APIs
   - Mitigation: Choose regions close to users
3. **Sentence Batching**: Wait for complete sentences before TTS
   - Trade-off: Prevents overlapping audio, adds slight delay

## Security Considerations

### API Keys
- ✅ Stored in `.env` file (not committed to git)
- ✅ Loaded via `python-dotenv`
- ✅ Never exposed to client

### WebSocket
- ⚠️ Currently no authentication
- For production: Add JWT token validation

### Audio Data
- ✅ Sent over WebSocket (can use WSS for encryption)
- ✅ Not stored on server (processed in memory)
- For production: Add audio encryption

### CORS
- ⚠️ Currently allows all origins (`allow_origins=["*"]`)
- For production: Restrict to specific domains

## Future Enhancements

### Short Term
1. **Faster TTS**: Replace gTTS with ElevenLabs or Deepgram Aura
2. **Authentication**: Add user login and session management
3. **Conversation Persistence**: Save chat history to database
4. **Multiple Voices**: Let users choose TTS voice

### Medium Term
1. **Multi-Language Support**: Detect language and switch STT/LLM/TTS
2. **Custom Wake Words**: "Hey Assistant" to activate
3. **Emotion Detection**: Adjust tone based on user sentiment
4. **Context Management**: Summarize long conversations

### Long Term
1. **On-Device Models**: Run VAD, STT, LLM locally for privacy
2. **Video Input**: Process visual context along with audio
3. **Multi-Modal Output**: Generate images, code, etc.
4. **Agent Tools**: Calendar, email, web search integration
