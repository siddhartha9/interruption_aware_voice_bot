# Technical Guide - Voice Bot Implementation

## Table of Contents
1. [System Design](#system-design)
2. [Core Components](#core-components)
3. [State Management](#state-management)
4. [Interruption Handling](#interruption-handling)
5. [Prompt Generation](#prompt-generation)
6. [Concurrency & Workers](#concurrency--workers)
7. [WebSocket Protocol](#websocket-protocol)
8. [Error Handling](#error-handling)
9. [Performance Optimization](#performance-optimization)
10. [Testing & Debugging](#testing--debugging)

---

## System Design

### Architecture Overview

The system follows a **client-server architecture** with **event-driven, asynchronous processing**:

```
┌──────────────────────────────────────────────┐
│              CLIENT (Browser)                │
│                                              │
│  Silero VAD → MediaRecorder → WebSocket     │
│                    ↓              ↑          │
│              Base64 Audio    JSON Events     │
└──────────────────────────────────────────────┘
                     ↕ WebSocket
┌──────────────────────────────────────────────┐
│           SERVER (FastAPI/Python)            │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │   ConnectionOrchestrator (Per User)    │ │
│  │                                        │ │
│  │  ┌──────┐  ┌──────┐  ┌──────┐       │ │
│  │  │ STT  │→ │ LLM  │→ │ TTS  │       │ │
│  │  │Worker│  │Worker│  │Worker│       │ │
│  │  └──────┘  └──────┘  └──────┘       │ │
│  │      ↕         ↕         ↕           │ │
│  │  [Queue]   [Queue]   [Queue]         │ │
│  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Design Principles

1. **Stateful per Connection**: Each WebSocket gets its own `ConnectionOrchestrator`
2. **Async/Await**: All I/O operations are non-blocking
3. **Queue-Based Decoupling**: Workers communicate via `asyncio.Queue`
4. **Event-Driven**: Client events drive server state transitions
5. **Immutable History**: Chat history is modified via copy-on-write

---

## Core Components

### 1. Connection Orchestrator

**File**: `src/server/orchestrator.py`

**Responsibility**: Central hub that manages state, coordinates workers, and handles events.

**Key Attributes**:
```python
class ConnectionOrchestrator:
    # Connection
    websocket: WebSocket
    session_id: str
    
    # State
    stt_status: Status
    agent_status: Status
    tts_status: Status
    playback_status: Status
    interruption_status: InterruptionStatus
    client_playback_active: bool
    response_in_progress: bool
    
    # Data Structures
    stt_job_queue: asyncio.Queue          # Audio buffers to transcribe
    stt_output_list: List[str]            # Completed transcriptions
    text_stream_queue: asyncio.Queue      # LLM → TTS
    audio_output_queue: AudioOutputQueue  # TTS → Client
    chat_history: List[Dict[str, str]]    # Conversation history
    
    # Workers
    stt_worker_handle: asyncio.Task
    tts_worker_handle: asyncio.Task
    llm_task_handle: asyncio.Task
    playback_worker: AudioPlaybackWorker
    
    # Modules
    stt_processor: STTProcessor
    ai_agent: AIAgent
    prompt_generator: PromptGenerator
    interruption_handler: InterruptionHandler
```

**Key Methods**:
```python
async def start_workers():
    """Start all background workers."""
    
async def handle_client_event(data: dict):
    """Route client events to appropriate handlers."""
    
async def on_user_starts_speaking():
    """Handle speech_start event (interruption detection)."""
    
async def on_user_ends_speaking(audio_base64: str):
    """Handle speech_end event (add to STT queue)."""
    
async def llm_processing_task():
    """Process STT outputs and call LLM (debounced)."""
    
async def run_agent_flow(chat_history):
    """Run agent and stream response to TTS."""
    
def is_system_idle() -> bool:
    """Check if all components are idle."""
```

### 2. STT Processor

**File**: `src/server/stt.py`

**Responsibility**: Convert audio to text using Deepgram Nova-2 API.

**Key Methods**:
```python
class STTProcessor:
    def __init__(self, api_key: str, model: str = "nova-2", language: str = "en"):
        self.client = DeepgramClient(api_key=api_key)
    
    async def transcribe_audio(self, audio_buffer: bytes) -> Optional[str]:
        """
        Transcribe audio buffer to text.
        
        Args:
            audio_buffer: Raw audio bytes (WebM/WAV)
        
        Returns:
            Transcribed text or None if failed
        """
        # 1. Detect audio format (WebM/WAV)
        encoding = self._detect_audio_format(audio_buffer)
        
        # 2. Call Deepgram API (in thread pool to avoid blocking)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.listen.v1.media.transcribe_file(
                request=audio_buffer,
                model=self.model,
                language=self.language,
                encoding=encoding,
                smart_format=True,
                punctuate=True
            )
        )
        
        # 3. Extract transcript from response
        return response.results.channels[0].alternatives[0].transcript
```

**Audio Format Detection**:
```python
def _detect_audio_format(self, audio_buffer: bytes) -> str:
    """Detect audio format from magic bytes."""
    # WAV: starts with b'RIFF' + b'WAVE'
    if audio_buffer[:4] == b'RIFF' and audio_buffer[8:12] == b'WAVE':
        return "wav"
    
    # WebM: starts with Matroska header
    if audio_buffer[:4] == b'\x1a\x45\xdf\xa3':
        return "webm"
    
    # Default fallback
    return "webm"
```

### 3. AI Agent

**File**: `src/server/ai_agent.py`

**Responsibility**: Generate conversational responses using Groq + LangGraph.

**Key Methods**:
```python
class AIAgent:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        # Initialize Groq LLM
        self.llm = ChatGroq(
            model=model,
            groq_api_key=api_key,
            temperature=0.7,
            streaming=True,  # Enable streaming
            max_retries=3,
            timeout=30.0
        )
        
        # Build LangGraph workflow
        self._build_graph()
    
    async def generate_response(
        self, 
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[Optional[str], None]:
        """
        Generate streaming response from chat history.
        
        Args:
            chat_history: [{"role": "user"|"assistant", "content": "..."}]
        
        Yields:
            Text chunks as they are generated
            None to signal end of stream
        """
        # Convert to LangChain format
        messages = [SystemMessage(content=self.system_prompt)]
        for msg in chat_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        
        # Stream from Groq
        async for chunk in self.llm.astream(messages):
            if self.is_cancelled:
                break
            if chunk.content:
                yield chunk.content
        
        yield None  # End of stream
    
    def cancel(self):
        """Cancel current generation."""
        self.is_cancelled = True
```

### 4. TTS Module

**File**: `src/server/tts.py`

**Responsibility**: Convert text to audio using gTTS.

**Key Function**:
```python
async def text_to_speech_base64(text: str) -> Optional[str]:
    """
    Convert text to audio and return as base64 string.
    
    Args:
        text: Text to convert to speech
    
    Returns:
        Base64-encoded MP3 audio or None if failed
    """
    try:
        # Run blocking gTTS call in thread pool
        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            lambda: _call_gtts_sync(text)
        )
        
        # Convert to base64
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        return audio_base64
        
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None

def _call_gtts_sync(text: str) -> bytes:
    """Synchronous gTTS call (runs in thread pool)."""
    tts = gTTS(text=text, lang='en')
    
    # Save to BytesIO
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    
    return audio_buffer.read()
```

### 5. Prompt Generator

**File**: `src/server/prompt_generator.py`

**Responsibility**: Intelligent prompt construction and chat history management.

**Key Methods**:
```python
class PromptGenerator:
    def generate_prompt(
        self,
        stt_output_list: List[str],
        chat_history: List[Dict[str, str]],
        is_interruption: bool
    ) -> Tuple[bool, str, List[Dict[str, str]]]:
        """
        Generate prompt and manage chat history.
        
        Returns:
            (is_new_prompt_needed, prompt, cleaned_history)
        """
        # 1. Merge all STT outputs
        all_new_text = self._merge_stt_outputs(stt_output_list)
        
        # 2. Check if false alarm (backchannel)
        if is_interruption and self._is_false_alarm(all_new_text):
            return False, all_new_text, chat_history
        
        # 3. Clean history if interruption
        if is_interruption:
            cleaned_history = self._clean_chat_history_on_interruption(
                chat_history, 
                all_new_text
            )
            return True, all_new_text, cleaned_history
        
        # 4. New turn - no changes
        return True, all_new_text, chat_history
```

**Chat History Cleaning**:
```python
def _clean_chat_history_on_interruption(
    self,
    chat_history: List[Dict[str, str]],
    new_user_text: str
) -> List[Dict[str, str]]:
    """
    Clean history on interruption:
    1. Remove unheard agent response
    2. Append new text to previous user message
    """
    if len(chat_history) == 0:
        return chat_history
    
    # Remove last agent message (if present)
    if chat_history[-1].get("role") == "agent":
        cleaned_history = chat_history[:-1].copy()
        
        # Append new text to previous user message
        if len(cleaned_history) > 0 and cleaned_history[-1].get("role") == "user":
            previous = cleaned_history[-1]["content"]
            cleaned_history[-1]["content"] = f"{previous} {new_user_text}"
        
        return cleaned_history
    
    return chat_history
```

**False Alarm Detection**:
```python
def _is_false_alarm(self, text: str) -> bool:
    """Detect backchannels like 'uh-huh', 'okay', 'mm-hmm'."""
    text_lower = text.lower().strip()
    
    false_alarm_phrases = [
        "uh-huh", "uhuh", "uh huh",
        "mm-hmm", "mmhmm", "mm hmm",
        "yeah", "yep", "yup",
        "okay", "ok", "k",
        "right", "sure",
        "got it", "i see",
        "go ahead",
    ]
    
    return text_lower in false_alarm_phrases
```

### 6. Interruption Handler

**File**: `src/server/interruption_handler.py`

**Responsibility**: Manage interruption actions (clear queues, cancel agent).

**Key Method**:
```python
class InterruptionHandler:
    async def handle_user_starts_speaking(
        self,
        agent_status: Status,
        ai_agent: AIAgent,
        text_stream_queue: asyncio.Queue,
        audio_output_queue: AudioOutputQueue
    ) -> Tuple[InterruptionStatus, bool]:
        """
        Handle interruption:
        1. Clear audio and text queues
        2. Cancel agent if still PROCESSING (not STREAMING)
        """
        # Always clear queues immediately
        audio_output_queue.clear()
        
        while not text_stream_queue.empty():
            try:
                text_stream_queue.get_nowait()
            except:
                break
        
        # Cancel agent if still PROCESSING
        agent_was_cancelled = False
        if agent_status == Status.PROCESSING:
            ai_agent.cancel()
            agent_was_cancelled = True
        
        return InterruptionStatus.ACTIVE, agent_was_cancelled
```

---

## State Management

### Status Enums

```python
class Status(Enum):
    IDLE = "idle"           # Not doing anything
    PROCESSING = "processing"  # Working on something (not yet outputting)
    STREAMING = "streaming"    # Outputting results
    ACTIVE = "active"       # Actively playing/working
    PAUSED = "paused"       # Temporarily stopped

class InterruptionStatus(Enum):
    IDLE = "idle"           # No interruption
    PROCESSING = "processing"  # Checking if interruption
    ACTIVE = "active"       # Confirmed interruption
```

### State Transitions

**Normal Flow**:
```
IDLE → PROCESSING → STREAMING → IDLE
```

**Interruption Flow**:
```
STREAMING → PAUSED → (check) → ACTIVE or IDLE
```

### System Idle Check

```python
def is_system_idle(self) -> bool:
    """
    Check if system is completely idle.
    
    Returns True only if:
    - All workers are IDLE
    - No client playback active
    - No response in progress
    """
    return (
        self.stt_status == Status.IDLE and
        self.agent_status == Status.IDLE and
        self.tts_status == Status.IDLE and
        self.playback_status == Status.IDLE and
        not self.client_playback_active and
        not self.response_in_progress
    )
```

---

## Interruption Handling

### The Pause-and-Decide Strategy

**Goal**: Handle user interruptions gracefully without losing context.

**Three Phases**:

#### Phase 1: User Starts Speaking (Event 1)

```python
async def on_user_starts_speaking(self):
    """
    Immediate reaction when user speaks.
    
    Logic:
    1. Check if system is idle → If yes, it's a new turn (no action)
    2. If system is busy → It's an interruption:
       a. Send stop_playback to client
       b. Set interruption_status = ACTIVE
       c. Clear audio and text queues
       d. Cancel agent if still PROCESSING
       e. Clear STT queue and output list (prevent stale data)
    """
    # Check if this is a new turn or interruption
    if self.is_system_idle():
        return  # New turn, do nothing
    
    # TRUE INTERRUPTION
    print("[Orchestrator] ⚠️ INTERRUPT DETECTED!")
    
    # Stop client audio immediately
    await self.websocket.send_json({"event": "stop_playback"})
    
    # Set interruption flag
    self.interruption_status = InterruptionStatus.ACTIVE
    
    # Handle interruption (clear queues, maybe cancel agent)
    await self.interruption_handler.handle_user_starts_speaking(
        self.agent_status,
        self.ai_agent,
        self.text_stream_queue,
        self.audio_output_queue
    )
    
    # Clear STT queue (prevent processing old audio)
    while not self.stt_job_queue.empty():
        self.stt_job_queue.get_nowait()
    
    # Clear STT output list (prevent using stale transcripts)
    self.stt_output_list.clear()
```

#### Phase 2: User Ends Speaking (Event 2)

```python
async def on_user_ends_speaking(self, audio_base64: str):
    """
    Simple producer: Add audio to STT queue.
    """
    # Decode base64 to bytes
    audio_bytes = base64.b64decode(audio_base64)
    
    # Add to STT job queue
    await self.stt_job_queue.put(audio_bytes)
    
    print(f"[Orchestrator] Audio buffer ({len(audio_bytes)} bytes) added to STT queue")
```

#### Phase 3: LLM Processing (The Decision)

```python
async def llm_processing_task(self):
    """
    Debounced task that decides: Resume or Regenerate?
    
    Flow:
    1. Wait briefly (debounce) to batch rapid utterances
    2. Merge all STT outputs
    3. Check if false alarm (backchannel)
    4. If false alarm → Resume playback
    5. If real interruption → Clean history & regenerate
    6. If new turn → Generate response
    """
    # Debounce (wait for more STT results)
    await asyncio.sleep(0.05)
    
    # Skip if agent is busy
    if self.agent_status in [Status.PROCESSING, Status.STREAMING]:
        return
    
    # Generate prompt and clean history
    is_new, prompt, cleaned_history = self.prompt_generator.generate_prompt(
        self.stt_output_list,
        self.chat_history,
        is_interruption=(self.interruption_status == InterruptionStatus.ACTIVE)
    )
    
    # Update history with cleaned version
    self.chat_history = cleaned_history
    self.stt_output_list.clear()
    
    # FALSE ALARM - Resume playback
    if not is_new and self.playback_status == Status.PAUSED:
        await self.websocket.send_json({"event": "playback_resume"})
        self.playback_status = Status.ACTIVE
        self.interruption_status = InterruptionStatus.IDLE
        return
    
    # REAL INTERRUPTION or NEW TURN - Regenerate
    self.ai_agent.cancel()
    self.audio_output_queue.clear()
    
    # Add new user message (if not interruption)
    if not is_interruption:
        self.chat_history.append({"role": "user", "content": prompt})
    
    # Reset states
    self.playback_status = Status.IDLE
    self.agent_status = Status.PROCESSING
    self.interruption_status = InterruptionStatus.IDLE
    self.response_in_progress = False
    
    # Call agent
    await self.run_agent_flow(self.chat_history)
```

### Chat History Management

**Problem**: When interrupted, the agent's response was never heard.

**Solution**: Append new text to previous user message.

**Example**:
```
Before Interruption:
  [1] USER: "How are you doing?"
  [2] AGENT: "I'm doing well..." [INTERRUPTED]

User says: "What are you doing?"

After Cleanup:
  [1] USER: "How are you doing? What are you doing?"
```

**Code**:
```python
# In PromptGenerator._clean_chat_history_on_interruption()
if chat_history[-1].get("role") == "agent":
    # Remove unheard agent response
    cleaned = chat_history[:-1].copy()
    
    # Append new text to previous user message
    if cleaned[-1].get("role") == "user":
        previous_text = cleaned[-1]["content"]
        cleaned[-1]["content"] = f"{previous_text} {new_user_text}"
    
    return cleaned
```

---

## Prompt Generation

### Merging STT Outputs

**Why**: Rapid speech can trigger multiple `speech_end` events.

**Solution**: Merge all transcripts before calling LLM.

```python
def _merge_stt_outputs(self, stt_output_list: List[str]) -> str:
    """
    Merge multiple STT outputs intelligently.
    
    Example:
      Input: ["Hello", "I want to", "book a flight"]
      Output: "Hello I want to book a flight"
    """
    if not stt_output_list:
        return ""
    
    # Join with spaces
    merged = " ".join(stt_output_list)
    
    # Clean up extra spaces
    merged = " ".join(merged.split())
    
    return merged.strip()
```

### False Alarm Detection

**Why**: User might say "uh-huh" or "okay" without wanting to interrupt.

**Solution**: Detect backchannels and resume playback.

```python
def _is_false_alarm(self, text: str) -> bool:
    """
    Detect if text is a backchannel (false alarm).
    
    Backchannels:
    - "uh-huh", "okay", "mm-hmm", "yeah", "right", etc.
    
    Returns True if it's a backchannel (don't regenerate).
    """
    text_lower = text.lower().strip()
    
    # List of common backchannels
    backchannels = [
        "uh-huh", "uhuh", "mm-hmm", "mmhmm",
        "yeah", "yep", "okay", "ok",
        "right", "sure", "got it", "go ahead"
    ]
    
    # Exact match
    if text_lower in backchannels:
        return True
    
    # Short text containing backchannel
    if len(text_lower.split()) <= 2:
        for phrase in backchannels:
            if phrase in text_lower:
                return True
    
    return False
```

---

## Concurrency & Workers

### Background Workers

**Why**: Decouple processing stages and enable concurrent operations.

#### STT Worker

```python
async def stt_worker(self):
    """
    Continuously process audio buffers from stt_job_queue.
    
    Flow:
    1. Wait for audio buffer from queue
    2. Transcribe using Deepgram
    3. Add result to stt_output_list
    4. Trigger LLM processing task
    """
    while True:
        try:
            # Get audio buffer
            audio_buffer = await self.stt_job_queue.get()
            
            # Transcribe
            self.stt_status = Status.PROCESSING
            text = await self.stt_processor.transcribe_audio(audio_buffer)
            self.stt_status = Status.IDLE
            
            # Add to output list
            if text:
                self.stt_output_list.append(text)
                print(f"[STT Worker] Transcript: '{text}'")
                
                # Trigger LLM task
                if not self.llm_task_handle or self.llm_task_handle.done():
                    self.llm_task_handle = asyncio.create_task(
                        self.llm_processing_task()
                    )
        
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[STT Worker] Error: {e}")
            self.stt_status = Status.IDLE
```

#### TTS Worker

```python
async def tts_worker(self):
    """
    Continuously convert text chunks to audio.
    
    Flow:
    1. Wait for text from text_stream_queue
    2. Convert to audio using gTTS
    3. Put audio in audio_output_queue
    4. Client pulls from audio_output_queue via WebSocket
    """
    while True:
        try:
            # Get text chunk
            text_chunk = await self.text_stream_queue.get()
            
            # End of stream signal
            if text_chunk is None:
                await self.audio_output_queue.put(None)
                self.tts_status = Status.IDLE
                continue
            
            # Generate audio
            self.tts_status = Status.PROCESSING
            audio_base64 = await text_to_speech_base64(text_chunk)
            
            # Send to client
            if audio_base64:
                await self.audio_output_queue.put(audio_base64)
        
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[TTS Worker] Error: {e}")
            self.tts_status = Status.IDLE
```

### Agent Flow

```python
async def run_agent_flow(self, chat_history):
    """
    Run agent and stream response to TTS.
    
    Flow:
    1. Call agent with chat history
    2. Buffer text until sentence complete
    3. Send complete sentences to TTS queue
    4. Add full response to chat history when done
    """
    try:
        self.response_in_progress = True
        self.agent_streamed_text_so_far = ""
        
        # Get text stream from agent
        text_stream = self.ai_agent.generate_response(chat_history)
        
        # Sentence batching
        text_buffer = ""
        sentence_delimiters = {'.', '!', '?', '\n'}
        final_response = ""
        
        async for text_chunk in text_stream:
            if text_chunk is None:
                break
            
            # Set status on first chunk
            if self.agent_status == Status.PROCESSING:
                self.agent_status = Status.STREAMING
            
            # Track all text
            final_response += text_chunk
            self.agent_streamed_text_so_far += text_chunk
            text_buffer += text_chunk
            
            # Check for sentence end
            if any(d in text_chunk for d in sentence_delimiters):
                if text_buffer.strip():
                    # Send complete sentence to TTS
                    await self.text_stream_queue.put(text_buffer)
                    text_buffer = ""
        
        # Send remaining text
        if text_buffer.strip():
            await self.text_stream_queue.put(text_buffer)
        
        # End of stream signal
        await self.text_stream_queue.put(None)
        
        # Add to chat history
        if final_response.strip():
            self.chat_history.append({
                "role": "agent",
                "content": final_response
            })
        
        self.agent_status = Status.IDLE
    
    except asyncio.CancelledError:
        print("[Agent Flow] Cancelled")
        self.agent_status = Status.IDLE
    except Exception as e:
        print(f"[Agent Flow] Error: {e}")
        self.agent_status = Status.IDLE
```

---

## WebSocket Protocol

### Client → Server Events

#### 1. `speech_start`
```json
{
  "type": "speech_start"
}
```
**When**: Silero VAD detects speech beginning

**Server Action**: Check for interruption

---

#### 2. `speech_end`
```json
{
  "type": "speech_end",
  "audio": "base64_encoded_audio_data"
}
```
**When**: Silero VAD detects speech ending

**Server Action**: Add audio to STT queue

---

#### 3. `client_playback_started`
```json
{
  "type": "client_playback_started"
}
```
**When**: Client starts playing first audio chunk

**Server Action**: Set `client_playback_active = True`

---

#### 4. `client_playback_complete`
```json
{
  "type": "client_playback_complete"
}
```
**When**: Client finishes playing all audio chunks

**Server Action**: Set `client_playback_active = False`, `response_in_progress = False`

---

### Server → Client Events

#### 1. `connected`
```json
{
  "event": "connected",
  "message": "Connected to Voice Bot Orchestrator",
  "session_id": "abc123"
}
```
**When**: WebSocket connection established

---

#### 2. `stop_playback`
```json
{
  "event": "stop_playback"
}
```
**When**: User interrupts (speech_start during playback)

**Client Action**: 
- Stop current audio
- Clear audio queue
- Reset playback state

---

#### 3. `play_audio`
```json
{
  "event": "play_audio",
  "audio": "base64_encoded_mp3_data"
}
```
**When**: TTS generates audio chunk

**Client Action**:
- Add to audio queue
- Play if not already playing

---

#### 4. `error`
```json
{
  "event": "error",
  "message": "Error description"
}
```
**When**: Server encounters error

---

## Error Handling

### STT Errors

**Common Issues**:
- Empty/corrupt audio
- Network timeout
- Invalid API key
- Audio format not supported

**Handling**:
```python
async def transcribe_audio(self, audio_buffer: bytes) -> Optional[str]:
    try:
        # Skip very small buffers
        if len(audio_buffer) < 5000:
            print("[STT] Audio too small, skipping")
            return None
        
        # Call API
        text = await self._call_deepgram_api(audio_buffer)
        return text
        
    except Exception as e:
        print(f"[STT] Error: {e}")
        return None  # Fail gracefully
```

### LLM Errors

**Common Issues**:
- Rate limiting (429)
- Network timeout
- Invalid API key
- Context too long

**Handling**:
```python
async def generate_response(...):
    try:
        async for chunk in self.llm.astream(messages):
            yield chunk.content
    
    except asyncio.CancelledError:
        # Interruption - expected
        print("[Agent] Cancelled")
        raise
    
    except Exception as e:
        # Unexpected error
        print(f"[Agent] Error: {e}")
        yield None  # End stream gracefully
```

### TTS Errors

**Common Issues**:
- gTTS rate limiting
- Network timeout
- Empty text
- Unicode issues

**Handling**:
```python
async def text_to_speech_base64(text: str) -> Optional[str]:
    try:
        # Run in thread pool
        audio_bytes = await loop.run_in_executor(None, lambda: _call_gtts_sync(text))
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None  # Client will skip this audio
```

### WebSocket Errors

**Handling**:
```python
try:
    # Main message loop
    while True:
        data = await websocket.receive_json()
        await orchestrator.handle_client_event(data)

except WebSocketDisconnect:
    print("[Server] Client disconnected")
    await orchestrator.cleanup()

except Exception as e:
    print(f"[Server] Error: {e}")
    await orchestrator.cleanup()
```

---

## Performance Optimization

### 1. Thread Pool for Blocking Calls

**Problem**: `gTTS` makes synchronous HTTP calls, blocking asyncio loop.

**Solution**: Run in thread pool.

```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(
    None,  # Use default thread pool
    blocking_function,
    *args
)
```

### 2. Sentence Batching

**Problem**: Streaming word-by-word causes overlapping audio.

**Solution**: Buffer text until sentence complete.

```python
text_buffer = ""
sentence_delimiters = {'.', '!', '?', '\n'}

for chunk in stream:
    text_buffer += chunk
    if any(d in chunk for d in sentence_delimiters):
        await tts_queue.put(text_buffer)
        text_buffer = ""
```

### 3. Queue Size Limits

**Problem**: Unbounded queues consume memory.

**Solution**: Set max sizes.

```python
text_stream_queue = asyncio.Queue(maxsize=50)
audio_output_queue = AudioOutputQueue(maxsize=20)
```

### 4. Debouncing LLM Calls

**Problem**: Rapid STT results trigger multiple LLM calls.

**Solution**: Wait briefly to batch.

```python
async def llm_processing_task(self):
    # Debounce: wait 50ms for more STT results
    await asyncio.sleep(0.05)
    
    # Merge all STT outputs
    text = merge(self.stt_output_list)
```

### 5. Efficient Queue Clearing

**Problem**: Interruptions leave stale data in queues.

**Solution**: Drain synchronously.

```python
# Clear entire queue without blocking
while not queue.empty():
    try:
        queue.get_nowait()
    except:
        break
```

---

## Testing & Debugging

### Debug Logging

**Enable verbose logging**:
```python
# In orchestrator
print(f"[Orchestrator] Current State:")
print(f"  STT: {self.stt_status}")
print(f"  Agent: {self.agent_status}")
print(f"  TTS: {self.tts_status}")
print(f"  Playback: {self.playback_status}")
print(f"  Interruption: {self.interruption_status}")
```

### Health Check

```bash
curl http://127.0.0.1:8000/health
```

**Expected**:
```json
{
  "status": "healthy",
  "deepgram_configured": true,
  "groq_configured": true,
  "groq_model": "llama-3.3-70b-versatile"
}
```

### Test STT

```python
# Manually trigger STT
audio_bytes = open("test.wav", "rb").read()
text = await stt_processor.transcribe_audio(audio_bytes)
print(f"Transcription: {text}")
```

### Test LLM

```python
# Test prompt
chat_history = [{"role": "user", "content": "Hello"}]
async for chunk in ai_agent.generate_response(chat_history):
    if chunk:
        print(chunk, end="", flush=True)
```

### Test TTS

```python
# Test audio generation
audio_base64 = await text_to_speech_base64("Hello world")
print(f"Generated {len(audio_base64)} bytes of base64 audio")
```

### Common Issues

**Issue**: No audio playing

**Debug**:
1. Check browser console for errors
2. Verify `play_audio` events sent
3. Check audio queue not empty
4. Test with `test_audio.html`

---

**Issue**: STT not detecting speech

**Debug**:
1. Check Deepgram API key
2. Verify audio format (WebM/WAV)
3. Check audio buffer size (>5000 bytes)
4. Test with `curl` and sample audio

---

**Issue**: Interruptions not working

**Debug**:
1. Check `is_system_idle()` logic
2. Verify `stop_playback` sent to client
3. Check client audio stops immediately
4. Verify queues cleared

---

This technical guide provides a comprehensive overview of the voice bot implementation. For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md). For usage instructions, see [README.md](README.md).

