"""
Conversation Orchestrator (Refactored).

This is the "brain" of the application. It coordinates all modules,
manages state, and orchestrates the conversation flow.
"""

import asyncio
from typing import List, Dict, Optional

# Import all modular components
from .state_types import Status, InterruptionStatus
from .stt import STTProcessor
from .ai_agent import AIAgent
from .tts import TTSError, text_to_speech_base64
from .audio_playback import AudioPlaybackWorker, AudioOutputQueue
from .interruption_handler import InterruptionHandler
from .prompt_generator import PromptGenerator


class ConnectionOrchestrator:
    """
    Manages the state and logic for a single WebSocket connection.
    
    This orchestrator coordinates:
    - VAD (Voice Activity Detection)
    - STT (Speech-to-Text)
    - AI Agent (LLM)
    - TTS (Text-to-Speech)
    - Audio Playback
    - Interruption Handling
    """
    
    def __init__(self, websocket, deepgram_api_key: str, groq_api_key: str, groq_model: str = "llama-3.3-70b-versatile"):
        """
        Initialize the orchestrator for a new connection.
        
        Args:
            websocket: WebSocket connection for this user
            deepgram_api_key: API key for Deepgram STT service
            groq_api_key: API key for Groq LLM
            groq_model: Groq model to use (default: llama-3.3-70b-versatile)
        """
        import uuid
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID
        print(f"[Orchestrator] Initializing new connection (Session: {self.session_id})...")
        self.websocket = websocket
        
        # --- State Variables ---
        self.stt_status = Status.IDLE
        self.agent_status = Status.IDLE
        self.tts_status = Status.IDLE
        self.tool_status = Status.IDLE
        self.client_playback_active = False  # Track if client is actively playing audio
        self.client_playback_was_active_before_interruption = False  # Track if client was playing before interruption (for false alarm resume)
        self.response_in_progress = False  # Track if we're in the middle of a response cycle
        self.current_generation_id = 0  # Track which response generation we're on
        
        # --- Data Queues & Lists ---
        self.stt_job_queue = asyncio.Queue()
        self.stt_output_list: List[str] = []
        self.text_stream_queue = asyncio.Queue(maxsize=50)  # Agent → TTS queue
        self.audio_output_queue = AudioOutputQueue(maxsize=20)
        self.chat_history: List[Dict[str, str]] = []
        
        # --- Background Task Handles ---
        self.llm_task_handle: Optional[asyncio.Task] = None
        self.stt_worker_handle: Optional[asyncio.Task] = None
        self.tts_worker_handle: Optional[asyncio.Task] = None
        
        
        self.stt_processor = STTProcessor(api_key=deepgram_api_key, model="nova-2", language="en")
        self.ai_agent = AIAgent(api_key=groq_api_key, model=groq_model, temperature=0.7)
        self.prompt_generator = PromptGenerator()
        
        self.playback_worker = AudioPlaybackWorker(
            websocket=self.websocket,
            audio_output_queue=self.audio_output_queue.get_raw_queue()
        )
        
        self.interruption_handler = InterruptionHandler()
        
        # --- Agent partial stream tracking (for interruptions) ---
        self.agent_streamed_text_so_far = ""
        self.agent_message_committed = False
    
    async def _ensure_playback_paused(self, reason: str, force_notify: bool = False):
        """
        Guarantee playback is paused when critical components are still active.
        
        Args:
            reason: Log message / client message for pausing playback
            force_notify: If True, always notify the client even if playback already paused
        """
        agent_active = self.agent_status in (Status.PROCESSING, Status.STREAMING)
        tts_streaming = (self.tts_status == Status.STREAMING)
        playback_active = (self.playback_status == Status.ACTIVE)
        client_flagged_active = self.client_playback_active
        
        should_pause = force_notify or agent_active or tts_streaming or playback_active or client_flagged_active
        if not should_pause:
            return
        
        notify_client = force_notify or playback_active or client_flagged_active
        if notify_client and self.websocket is not None:
            await self.websocket.send_json({
                "event": "stop_playback",
                "message": reason
            })
            print(f"[Orchestrator] Sent stop_playback ({reason}) "
                  f"[agent_active={agent_active}, tts_streaming={tts_streaming}, playback_active={playback_active}]")
        
        if self.playback_status != Status.PAUSED:
            self.playback_status = Status.PAUSED
            print("[Orchestrator] Playback forced to PAUSED while agent/TTS are active.")
        
        if self.client_playback_active:
            self.client_playback_active = False
            print("[Orchestrator] client_playback_active set to False (pause enforced).")
    
    @property
    def playback_status(self) -> Status:
        """Get current playback status."""
        return self.playback_worker.get_status()
    
    @playback_status.setter
    def playback_status(self, status: Status):
        """Set playback status."""
        if status == Status.ACTIVE:
            self.playback_worker.set_active()
        elif status == Status.PAUSED:
            self.playback_worker.pause()
        elif status == Status.IDLE:
            self.playback_worker.set_idle()
    
    @property
    def interruption_status(self) -> InterruptionStatus:
        """Get current interruption status."""
        return self.interruption_handler.get_status()
    
    @interruption_status.setter
    def interruption_status(self, status: InterruptionStatus):
        """Set interruption status."""
        self.interruption_handler.set_status(status)
    
    def is_system_idle(self) -> bool:
        """Check if the system is completely at rest."""
        return (self.stt_status == Status.IDLE and
                self.agent_status == Status.IDLE and
                self.tts_status == Status.IDLE and
                self.tool_status == Status.IDLE and
                self.playback_status == Status.IDLE and
                not self.client_playback_active and  # Client must also be idle
                not self.response_in_progress)  # Not in middle of generating response
    
    async def start_workers(self):
        """Start the long-running background tasks for this connection."""
        print("[Orchestrator] Starting background workers...")
        self.stt_worker_handle = asyncio.create_task(self.stt_worker())
        self.tts_worker_handle = asyncio.create_task(self.tts_worker())
        await self.playback_worker.start()
        print("[Orchestrator] All workers started")
    
    async def cleanup(self):
        """Cancel all background tasks on disconnect."""
        print("[Orchestrator] Cleaning up connection...")
        
        # Cancel STT worker
        if self.stt_worker_handle:
            self.stt_worker_handle.cancel()
        
        # Cancel TTS worker
        if self.tts_worker_handle:
            self.tts_worker_handle.cancel()
        
        # Stop playback worker
        await self.playback_worker.stop()
        
        # Clear queues (prevent stale data)
        self.audio_output_queue.clear()
        while not self.text_stream_queue.empty():
            try:
                self.text_stream_queue.get_nowait()
            except:
                break
        
        # Cancel LLM task
        if self.llm_task_handle and not self.llm_task_handle.done():
            self.llm_task_handle.cancel()
        
        # Cancel AI agent and tools
        self.ai_agent.cancel()
        
        print("[Orchestrator] Cleanup complete")
    
    # --- 3. Client Event Handlers ---
    
    async def handle_client_event(self, event: Dict):
        """
        Main entry point for client events.
        
        The client runs VAD locally and sends structured events.
        
        Args:
            event: Event dict with 'type' and optional 'audio' keys
                  Types: 'speech_start', 'speech_end', 'audio_chunk'
        """
        event_type = event.get('type')
        
        if event_type == 'speech_start':
            # User started speaking (detected by client VAD)
            await self.on_user_starts_speaking()
        
        elif event_type == 'speech_end':
            # User stopped speaking, audio buffer included
            audio_data = event.get('audio')
            if audio_data:
                # Decode base64 if necessary
                if isinstance(audio_data, str):
                    import base64
                    audio_bytes = base64.b64decode(audio_data)
                else:
                    audio_bytes = audio_data
                
                await self.on_user_ends_speaking(audio_bytes)
            else:
                print("[Orchestrator] Warning: speech_end event without audio data")
        
        elif event_type == 'client_playback_started':
            # Client started playing audio
            self.client_playback_active = True
            print("[Orchestrator] Client playback ACTIVE")
        
        elif event_type == 'client_playback_complete':
            # Client finished playing all audio
            self.client_playback_active = False
            # Only clear response_in_progress if we're not already in a new cycle
            # (i.e., if agent is idle and not generating)
            if self.agent_status == Status.IDLE:
                self.response_in_progress = False
                print("[Orchestrator] Client playback COMPLETE (IDLE, response_in_progress = False)")
            else:
                print("[Orchestrator] Client playback COMPLETE (but new response already started, keeping response_in_progress = True)")
    
    async def on_user_starts_speaking(self):
        """
        Event 1: The "Pause" Reaction.
        
        Reacts immediately to user speech. If it's an interruption, pause playback.
        """
        print(f"\n{'='*60}")
        print(f"--- EVENT 1: User Starts Speaking ---")
        print(f"{'='*60}")
        print(f"[Orchestrator] 🔍 Current State Check:")
        print(f"  • STT Status: {self.stt_status}")
        print(f"  • Agent Status: {self.agent_status}")
        print(f"  • TTS Status: {self.tts_status}")
        print(f"  • Playback Status: {self.playback_status}")
        print(f"  • Interruption Status: {self.interruption_status}")
        print(f"  • Client Playback Active: {self.client_playback_active}")
        print(f"  • Response In Progress: {self.response_in_progress}")
        
        # If the system is idle, it's a new turn. Do nothing.
        is_idle = self.is_system_idle()
        print(f"\n[Orchestrator] is_system_idle() = {is_idle}")
        
        if is_idle:
            print("[Orchestrator] ✓ System is IDLE. This is a new turn (not an interruption).")
            return
        
        # --- If we are here, this is a TRUE interruption ---
        print("[Orchestrator] ⚠️ INTERRUPT DETECTED!")
        print(f"[Orchestrator] Current playback_status: {self.playback_status}")
        
        # Save client playback state BEFORE forcing pause (for false alarm resume)
        client_was_playing = self.client_playback_active
        
        # Ensure playback is paused while agent/TTS are still active
        await self._ensure_playback_paused(
            reason="Interruption detected",
            force_notify=True
        )
        
        self.client_playback_was_active_before_interruption = client_was_playing
        print(f"[Orchestrator] Saved client playback state: {self.client_playback_was_active_before_interruption}")
        
        # Clear STT job queue (prevent processing old audio buffers)
        cleared_stt_jobs = 0
        while not self.stt_job_queue.empty():
            try:
                self.stt_job_queue.get_nowait()
                cleared_stt_jobs += 1
            except:
                break
        if cleared_stt_jobs > 0:
            print(f"[Orchestrator] Cleared {cleared_stt_jobs} pending STT jobs")
        
        # Clear STT output list (prevent stale transcripts from being processed)
        if self.stt_output_list:
            cleared_count = len(self.stt_output_list)
            self.stt_output_list.clear()
            print(f"[Orchestrator] Cleared {cleared_count} pending STT transcripts")
        
        # Handle server-side interruption logic (cancel agent, clear queues)
        new_interruption_status, agent_was_cancelled = \
            await self.interruption_handler.handle_user_starts_speaking(
                agent_status=self.agent_status,
                ai_agent=self.ai_agent,
                text_stream_queue=self.text_stream_queue,
                audio_output_queue=self.audio_output_queue
            )
        
        # Update states
        self.interruption_status = new_interruption_status
        
        # If agent was cancelled, set its status to IDLE
        if agent_was_cancelled:
            self.agent_status = Status.IDLE
            self.tts_status = Status.IDLE  # TTS should also be reset
            print("[Orchestrator] ✓ Agent and TTS status reset to IDLE.")
        
        print(f"[Orchestrator] Interruption status set to: {self.interruption_status}")

    
    async def on_user_ends_speaking(self, complete_audio_buffer: bytes):
        """
        Event 2: The "Audio Producer".
        
        Adds the user's completed audio to the STT job queue.
        
        Args:
            complete_audio_buffer: Complete audio buffer from the user
        """
        import time
        timestamp = time.strftime('%H:%M:%S')
        print(f"\n{'='*60}")
        print(f"--- EVENT 2: User Ends Speaking (Buffer: {len(complete_audio_buffer)} bytes) ---")
        print(f"[Orchestrator] ⏱️  Timestamp: {timestamp}")
        print(f"{'='*60}")
        
        # Add the new audio buffer to the job queue for the STT worker
        if complete_audio_buffer:
            await self.stt_job_queue.put(complete_audio_buffer)
        else:
            print("[Orchestrator] Empty audio buffer, skipping STT.")
    
    # --- 4. Background Workers (The "Brain") ---
    
    async def stt_worker(self):
        """
        Worker: The "Text Producer".
        
        Runs in a loop, converting audio buffers into text summaries
        and triggering the LLM task.
        """
        print("  [STT Worker] Started. Waiting for jobs...")
        while True:
            try:
                # 1. Get the next audio buffer to process
                buffer_to_process = await self.stt_job_queue.get()
                print("  [STT Worker] Got new job.")
                
                # 2. Handle STT Process
                self.stt_status = Status.PROCESSING
                text_summary = await self.stt_processor.transcribe_audio(buffer_to_process)
                self.stt_status = Status.IDLE
                
                if text_summary:
                    print(f"  [STT Worker] Transcript: '{text_summary}'")
                    
                    # 3. Add the summary to the output list
                    self.stt_output_list.append(text_summary)
                    
                    # 4. Trigger the LLM processor
                    if self.llm_task_handle and not self.llm_task_handle.done():
                        # If LLM task is already debouncing, cancel it
                        # to restart the debounce timer
                        self.llm_task_handle.cancel()
                    
                    self.llm_task_handle = asyncio.create_task(self.llm_processing_task())
                else:
                    # STT returned no text (no speech detected - could be noise or error)
                    print("  [STT Worker] STT returned no text (no speech detected).")
                    
                    # Only handle as interruption if there was actually an interruption
                    # Check if we're in an interruption state or have saved interruption state
                    has_interruption_state = (
                        self.interruption_status == InterruptionStatus.ACTIVE or
                        self.client_playback_was_active_before_interruption or
                        self.playback_status == Status.PAUSED
                    )
                    
                    if has_interruption_state:
                        # This was an interruption that turned out to be noise - handle resume
                        await self.handle_empty_stt_after_interruption()
                    else:
                        # No interruption - just noise during idle state, ignore it
                        print("  [STT Worker] No interruption detected - ignoring empty STT (just noise).")
                
                self.stt_job_queue.task_done()
            
            except asyncio.CancelledError:
                print("  [STT Worker] Shutting down...")
                break
            except Exception as e:
                print(f"  [STT Worker] ERROR: {e}")
                self.stt_status = Status.IDLE
    
    async def handle_empty_stt_after_interruption(self):
        """
        Handle case when STT returns no text after an interruption.
        
        This happens when the user interrupts, but STT detects only noise
        (no actual speech). In this case:
        
        1. If playback is paused → resume playback (false alarm - just noise)
        2. If agent is streaming/processing → continue with current response (don't interrupt)
           The agent will continue using the previous chat history (no new user input)
        3. If agent is IDLE but has pending chat history → restart agent with previous chat history
           This happens when the agent was cancelled during interruption but STT found no speech
           The agent will use the previous chat history (no new user input)
        4. If system is idle → just reset interruption status (no action needed)
        """
        print("  [STT Worker] Handling empty STT after interruption (noise detected)...")
        
        # Check if this was an interruption (interruption status is active OR we have saved state)
        # We check both current status and saved state because the status might have been reset
        # before STT completed (e.g., if STT took a long time)
        is_interruption_active = (self.interruption_status == InterruptionStatus.ACTIVE)
        has_saved_interruption_state = (
            self.client_playback_was_active_before_interruption or
            self.playback_status == Status.PAUSED or
            self.response_in_progress
        )
        
        is_interruption = is_interruption_active or has_saved_interruption_state
        
        print(f"  [STT Worker] Interruption check:")
        print(f"    interruption_status == ACTIVE: {is_interruption_active}")
        print(f"    client_playback_was_active_before: {self.client_playback_was_active_before_interruption}")
        print(f"    playback_status == PAUSED: {self.playback_status == Status.PAUSED}")
        print(f"    response_in_progress: {self.response_in_progress}")
        print(f"    is_interruption: {is_interruption}")
        
        if not is_interruption:
            # Not an interruption - just noise during idle state
            print("  [STT Worker] No interruption detected. Ignoring noise.")
            return
        
        # This is an interruption that turned out to be noise
        print("  [STT Worker] ⚠️  Interruption detected but no speech found (false alarm/noise)")
        
        # Handle playback first (independent of agent status)
        # Resume if playback was paused OR if client was playing before interruption
        playback_was_paused = (self.playback_status == Status.PAUSED)
        client_was_playing_before = self.client_playback_was_active_before_interruption
        was_generating_response = self.response_in_progress
        
        should_resume_playback = (
            playback_was_paused or
            client_was_playing_before or
            was_generating_response
        )
        
        if should_resume_playback:
            print("  [STT Worker] 📢 Resuming playback (false alarm)")
            print(f"  [STT Worker]   Server playback paused: {playback_was_paused}")
            print(f"  [STT Worker]   Client was playing before: {client_was_playing_before}")
            print(f"  [STT Worker]   Response was in progress: {was_generating_response}")
            
            # Check if there's audio in the server queue
            has_audio_in_queue = not self.audio_output_queue.empty()
            
            # Send resume event to client
            await self.websocket.send_json({"event": "playback_resume"})
            print("  [STT Worker] ✅ Sent playback_resume event to client")
            
            # Update server-side playback status
            if playback_was_paused:
                if has_audio_in_queue:
                    # Server has audio - resume server playback
                    self.playback_status = Status.ACTIVE
                    self.client_playback_active = True
                    print("  [STT Worker] ✅ Resumed server playback (audio in queue)")
                else:
                    # Server has no audio - set to IDLE (client will handle resume)
                    self.playback_status = Status.IDLE
                    self.client_playback_active = True
                    print("  [STT Worker] ✅ Server playback set to IDLE (client will handle resume)")
            elif client_was_playing_before or was_generating_response:
                # Client was playing or we were generating - mark client as active
                self.client_playback_active = True
                print("  [STT Worker] ✅ Client playback marked as active (client will resume if it has audio)")
            
            # Reset the "before interruption" flag
            self.client_playback_was_active_before_interruption = False
        
        # Handle agent status (independent of playback)
        # Case 1: Agent is streaming/processing → Continue with current response
        # The agent is already generating a response using the previous chat history
        # No new prompt is needed - just let it continue
        if self.agent_status in (Status.STREAMING, Status.PROCESSING):
            agent_status_str = "STREAMING" if self.agent_status == Status.STREAMING else "PROCESSING"
            print(f"  [STT Worker] 🔄 Agent is {agent_status_str} → Continuing with current response")
            print(f"  [STT Worker]    (No new prompt needed - noise detected)")
            print(f"  [STT Worker]    (Agent will continue using previous chat history)")
            # Don't interrupt the agent - let it continue
            # The agent is already using the previous chat history and will continue streaming
            self.interruption_status = InterruptionStatus.IDLE
            print(f"  [STT Worker] ✅ Interruption status reset. Agent continues {agent_status_str.lower()}.")
            return
        
        # Case 2: Agent is IDLE but has pending chat history → Restart agent with previous chat history
        # This happens when the agent was cancelled during interruption but STT found no speech
        # We should restart the agent with the previous chat history (no new user input)
        if self.agent_status == Status.IDLE and len(self.chat_history) > 0:
            # Check if the last message is from user (agent was cancelled before responding)
            last_message = self.chat_history[-1]
            if last_message.get("role") == "user":
                print("  [STT Worker] 🔄 Agent is IDLE but has pending user message → Restarting with previous chat history")
                print(f"  [STT Worker]    (No new prompt needed - noise detected)")
                print(f"  [STT Worker]    (Using previous chat history: {len(self.chat_history)} messages)")
                
                # Clear any pending audio/text queues (cleanup from interruption)
                self.audio_output_queue.clear()
                # Clear text queue
                while not self.text_stream_queue.empty():
                    try:
                        self.text_stream_queue.get_nowait()
                    except:
                        break
                
                # Reset states for new response
                # Note: playback might have been resumed above (if it was paused)
                # We set playback to IDLE so AudioPlaybackWorker can auto-activate on new audio
                # (If playback was paused, we already resumed it above, so this ensures clean state)
                self.playback_status = Status.IDLE
                self.agent_status = Status.PROCESSING
                self.interruption_status = InterruptionStatus.IDLE
                self.response_in_progress = False
                self.current_generation_id += 1
                
                print(f"  [STT Worker] 🔄 Restarting agent with previous chat history (generation_id={self.current_generation_id})")
                
                # Log the chat history being used
                print("\n" + "="*60)
                print("  [STT Worker] 🤖 RESTARTING AGENT WITH PREVIOUS CHAT HISTORY:")
                print("="*60)
                print(f"  Chat History Length: {len(self.chat_history)} messages")
                for i, msg in enumerate(self.chat_history):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    print(f"  [{i+1}] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")
                print("="*60 + "\n")
                
                # Restart agent flow with previous chat history (no new user input)
                self.llm_task_handle = asyncio.create_task(
                    self.run_agent_flow(self.chat_history)
                )
                
                print("  [STT Worker] ✅ Agent restarted with previous chat history.")
                return
        
        # Case 3: System is completely idle → Just reset interruption status
        # No action needed - system is idle, noise was detected but nothing to resume/restart
        if self.agent_status == Status.IDLE and self.playback_status == Status.IDLE:
            print("  [STT Worker] 💤 System is idle → No action needed")
            self.interruption_status = InterruptionStatus.IDLE
            print("  [STT Worker] ✅ Interruption status reset.")
            return
        
        # Default: Reset interruption status
        # (Edge case: playback was resumed but agent is in an unexpected state)
        self.interruption_status = InterruptionStatus.IDLE
        print("  [STT Worker] ✅ Interruption status reset.")
    
    async def llm_processing_task(self):
        """
        Worker: The "Decision Maker".
        
        Runs after being triggered (with a debounce), "batches" all new
        text summaries, and decides whether to resume or regenerate.
        """
        try:
            # 1. Debounce/Coalesce
            print("    [LLM Task] Triggered. Debouncing...")
            await asyncio.sleep(0.1)  # 100ms debounce
        except asyncio.CancelledError:
            print("    [LLM Task] Debounce cancelled.")
            return
        
        try:
            # 2. Check if Busy
            if self.agent_status in (Status.PROCESSING, Status.STREAMING):
                print("    [LLM Task] Agent is busy. Will let current run finish.")
                return
            
            print("    [LLM Task] Starting LLM processing...")
            
            # CRITICAL: Check if we're in an interruption state even if stt_output_list is empty
            # This can happen if:
            # 1. llm_processing_task was triggered and debouncing
            # 2. During debounce, interruption happens and clears stt_output_list
            # 3. When task runs, stt_output_list is empty but we're still in interruption
            # 4. We need to check if this is a false alarm and resume playback
            is_interruption = (self.interruption_status == InterruptionStatus.ACTIVE)
            has_interruption_state = (
                is_interruption or
                self.client_playback_was_active_before_interruption or
                self.playback_status == Status.PAUSED
            )
            
            if not self.stt_output_list:
                print("    [LLM Task] No text to process.")
                
                # If we're in an interruption state but have no text, this might be a false alarm
                # Check if we should resume playback
                if has_interruption_state:
                    print("    [LLM Task] ⚠️ Empty STT but interruption state detected - checking for false alarm resume...")
                    
                    playback_was_paused = (self.playback_status == Status.PAUSED)
                    client_was_playing_before = self.client_playback_was_active_before_interruption
                    was_generating_response = self.response_in_progress
                    agent_is_still_active = self.agent_status in (Status.STREAMING, Status.PROCESSING)
                    
                    # If playback was paused or client was playing, this is likely a false alarm
                    # (no actual speech, just noise during interruption)
                    should_resume = (
                        playback_was_paused or
                        client_was_playing_before or
                        (was_generating_response and not agent_is_still_active)
                    )
                    
                    if should_resume:
                        print("    [LLM Task] 📢 False alarm detected (empty STT during interruption) - Resuming playback")
                        
                        # Check if there's audio in the server queue
                        has_audio_in_queue = not self.audio_output_queue.empty()
                        
                        # Send resume event to client
                        await self.websocket.send_json({"event": "playback_resume"})
                        print("    [LLM Task] ✅ Sent playback_resume event to client")
                        
                        # Update server-side playback status
                        if playback_was_paused:
                            if has_audio_in_queue:
                                self.playback_status = Status.ACTIVE
                                self.client_playback_active = True
                                print("    [LLM Task] ✅ Resumed server playback (audio in queue)")
                            else:
                                self.playback_status = Status.IDLE
                                self.client_playback_active = True
                                print("    [LLM Task] ✅ Server playback set to IDLE (client will handle resume)")
                        elif client_was_playing_before or was_generating_response:
                            self.client_playback_active = True
                            print("    [LLM Task] ✅ Client playback marked as active (client will resume if it has audio)")
                        
                        # Reset interruption state
                        self.client_playback_was_active_before_interruption = False
                        self.interruption_status = InterruptionStatus.IDLE
                        print("    [LLM Task] ✅ Interruption status reset.")
                        return
                    
                    # If we shouldn't resume playback, check if there's pending chat history to process
                    # This happens when:
                    # 1. Interruption was detected (noise/false alarm)
                    # 2. But no playback was active (wasn't paused)
                    # 3. Agent is IDLE
                    # 4. There's pending chat history (user message waiting for response)
                    if not should_resume and self.agent_status == Status.IDLE and len(self.chat_history) > 0:
                        # Check if the last message is from user (agent hasn't responded yet)
                        last_message = self.chat_history[-1]
                        if last_message.get("role") == "user":
                            print("    [LLM Task] 🔄 Interruption detected but no playback to resume")
                            print("    [LLM Task]    Checking for pending chat history...")
                            print(f"    [LLM Task]    Found pending user message → Processing chat history")
                            print(f"    [LLM Task]    Chat history length: {len(self.chat_history)} messages")
                            
                            # Tell client to discard any buffered audio from the interrupted response
                            await self.websocket.send_json({"event": "playback_reset"})
                            print("    [LLM Task] ⚠️ Sent playback_reset event to client (discard stale audio)")
                            
                            # Make sure client/server playback flags reflect the reset state
                            self.client_playback_active = False
                            
                            # Clear any pending audio/text queues (cleanup from interruption)
                            self.audio_output_queue.clear()
                            # Clear text queue
                            while not self.text_stream_queue.empty():
                                try:
                                    self.text_stream_queue.get_nowait()
                                except:
                                    break
                            
                            # Reset states for new response
                            self.playback_status = Status.IDLE
                            self.agent_status = Status.PROCESSING
                            self.interruption_status = InterruptionStatus.IDLE
                            self.response_in_progress = False
                            self.current_generation_id += 1
                            self.client_playback_was_active_before_interruption = False
                            
                            print(f"    [LLM Task] 🔄 Processing pending chat history (generation_id={self.current_generation_id})")
                            
                            # Log the chat history being used
                            print("\n" + "="*60)
                            print("    [LLM Task] 🤖 PROCESSING PENDING CHAT HISTORY:")
                            print("="*60)
                            print(f"    Chat History Length: {len(self.chat_history)} messages")
                            for i, msg in enumerate(self.chat_history):
                                role = msg.get('role', 'unknown')
                                content = msg.get('content', '')
                                print(f"    [{i+1}] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")
                            print("="*60 + "\n")
                            
                            # Process chat history (no new user input - just process existing history)
                            self.llm_task_handle = asyncio.create_task(
                                self.run_agent_flow(self.chat_history)
                            )
                            
                            print("    [LLM Task] ✅ Agent started processing pending chat history.")
                            return
                    
                    # If we get here, we have an interruption state but:
                    # - No playback to resume
                    # - No pending chat history to process
                    # - Just reset interruption status
                    print("    [LLM Task] 💤 Interruption state detected but nothing to resume/process")
                    print("    [LLM Task]    Resetting interruption status...")
                    self.client_playback_was_active_before_interruption = False
                    self.interruption_status = InterruptionStatus.IDLE
                    print("    [LLM Task] ✅ Interruption status reset.")
                    return
                
                return
            
            # 3. Generate prompt by merging ALL STT outputs and cleaning chat history if needed
            # The Prompt Generator handles:
            # - Merging all STT outputs into coherent text
            # - Removing unheard agent responses during interruptions
            # - Detecting false alarms (backchannels like "uh-huh")
            is_interruption = (self.interruption_status == InterruptionStatus.ACTIVE)
            
            is_new_prompt_needed, user_prompt, cleaned_history = self.prompt_generator.generate_prompt(
                stt_output_list=self.stt_output_list,  # ALL STT outputs merged here
                chat_history=self.chat_history,
                is_interruption=is_interruption
            )
            
            # Update chat history with cleaned version (if interruption occurred)
            self.chat_history = cleaned_history
            
            # Consume the text
            self.stt_output_list.clear()
            
            # 4. --- THE DECISION ---
            # Check if we should skip regeneration (false alarm during interruption)
            # If this is a false alarm AND we're in an interruption state, we should resume playback
            playback_was_paused = (self.playback_status == Status.PAUSED)
            client_was_playing_before = self.client_playback_was_active_before_interruption
            was_generating_response = self.response_in_progress
            
            # Resume if:
            # 1. This is a false alarm (not a new prompt needed - e.g., "Mhmm", "uh-huh")
            # 2. AND we're in an interruption state (we paused playback during interruption)
            # The client or server will handle resuming if there's audio to resume
            is_false_alarm = not is_new_prompt_needed
            is_in_interruption = is_interruption  # We're in an interruption state
            
            # Log state for debugging
            print(f"    [LLM Task] False alarm check:")
            print(f"      is_false_alarm: {is_false_alarm}")
            print(f"      is_in_interruption: {is_in_interruption}")
            print(f"      playback_was_paused: {playback_was_paused}")
            print(f"      client_was_playing_before: {client_was_playing_before}")
            print(f"      was_generating_response: {was_generating_response}")
            
            if is_false_alarm and is_in_interruption:
                # --- PATH A: FALSE ALARM (e.g., "Mhmm", "uh-huh") ---
                print(f"    [LLM Task] FALSE ALARM: '{user_prompt}'")
                print(f"    [LLM Task] Server playback status: {self.playback_status}")
                print(f"    [LLM Task] Client was playing before interruption: {client_was_playing_before}")
                print(f"    [LLM Task] Response was in progress: {was_generating_response}")
                
                # Check if there's audio in the server queue
                has_audio_in_queue = not self.audio_output_queue.empty()
                
                # Check if agent is still streaming/processing (response was in progress when interrupted)
                agent_is_still_active = self.agent_status in (Status.STREAMING, Status.PROCESSING)
                tts_is_streaming = (self.tts_status == Status.STREAMING)
                
                if (agent_is_still_active or tts_is_streaming) and self.playback_status != Status.PAUSED:
                    await self._ensure_playback_paused(
                        reason="Maintaining pause while agent/TTS active during interruption resume check",
                        force_notify=False
                    )
                
                # Decision: Should we resume playback OR process pending chat history?
                # Resume if playback was paused or client was playing
                should_resume_playback = (
                    not agent_is_still_active and
                    not tts_is_streaming and
                    (
                    playback_was_paused or
                    client_was_playing_before or
                        was_generating_response
                    )
                )
                
                if should_resume_playback:
                    # --- PATH A1: Resume playback ---
                    print(f"    [LLM Task] 📢 Resuming playback (false alarm during active playback)")
                    print(f"    [LLM Task] Server audio queue empty: {self.audio_output_queue.empty()}")
                    print(f"    [LLM Task] Agent still active: {agent_is_still_active} (status: {self.agent_status})")
                    
                    # Always send resume event to client (client may have audio queued on its side)
                    # The client's resume handler will check if it has audio to resume
                    await self.websocket.send_json({"event": "playback_resume"})
                    print(f"    [LLM Task] ✅ Sent playback_resume event to client")
                    
                    # Update server-side playback status based on what we have
                    if playback_was_paused:
                        # Server playback was paused - resume it if we have audio or agent is still active
                        if has_audio_in_queue:
                            # Server has audio - resume server playback immediately
                            self.playback_status = Status.ACTIVE
                            self.client_playback_active = True
                            print(f"    [LLM Task] ✅ Resumed server playback (audio in queue)")
                        elif agent_is_still_active:
                            # Agent is still generating - new audio will arrive soon
                            # Set playback to IDLE so AudioPlaybackWorker will auto-activate when new audio arrives
                            self.playback_status = Status.IDLE
                            self.client_playback_active = True
                            print(f"    [LLM Task] ✅ Server playback set to IDLE (agent still generating, will resume on new audio)")
                        else:
                            # Server has no audio and agent is done - let client handle resume from its queue
                            # Client might have audio queued that wasn't played yet
                            self.playback_status = Status.IDLE
                            self.client_playback_active = True
                            print(f"    [LLM Task] ✅ Server playback set to IDLE (client will handle resume from its queue)")
                    elif client_was_playing_before or was_generating_response:
                        # Client was playing or we were generating - mark client as active
                        # If agent is still active, audio will continue streaming
                        self.client_playback_active = True
                        # If agent is still active, ensure playback is ready to receive audio
                        if agent_is_still_active and self.playback_status == Status.IDLE:
                            # Agent is still generating, but playback is IDLE
                            # This is fine - AudioPlaybackWorker will auto-activate when new audio arrives
                            print(f"    [LLM Task] ✅ Client playback marked as active (agent still generating, audio will continue)")
                        else:
                            # Client will resume from its own queue if it has audio
                            print(f"    [LLM Task] ✅ Client playback marked as active (client will resume if it has audio)")
                    
                    # Reset the "before interruption" flag
                    self.client_playback_was_active_before_interruption = False
                    self.interruption_status = InterruptionStatus.IDLE
                    print(f"    [LLM Task] ✅ Interruption status reset.")
                    return
                
                else:
                    # --- PATH A2: No playback to resume, check for pending chat history ---
                    # This happens when:
                    # 1. False alarm detected (e.g., "Mhmm")
                    # 2. But no playback was active (wasn't paused)
                    # 3. Agent is IDLE
                    # 4. There's pending chat history (user message waiting for response)
                    if self.agent_status == Status.IDLE and len(self.chat_history) > 0:
                        # Check if the last message is from user (agent hasn't responded yet)
                        last_message = self.chat_history[-1]
                        if last_message.get("role") == "user":
                            print("    [LLM Task] 🔄 False alarm detected but no playback to resume")
                            print("    [LLM Task]    Checking for pending chat history...")
                            print(f"    [LLM Task]    Found pending user message → Processing chat history")
                            print(f"    [LLM Task]    Chat history length: {len(self.chat_history)} messages")
                            
                            # Tell client to discard any buffered audio from the interrupted response
                            await self.websocket.send_json({"event": "playback_reset"})
                            print("    [LLM Task] ⚠️ Sent playback_reset event to client (discard stale audio)")
                            
                            # Make sure client/server playback flags reflect the reset state
                            self.client_playback_active = False
                            
                            # Clear any pending audio/text queues (cleanup from interruption)
                            self.audio_output_queue.clear()
                            # Clear text queue
                            while not self.text_stream_queue.empty():
                                try:
                                    self.text_stream_queue.get_nowait()
                                except:
                                    break
                            
                            # Reset states for new response
                            self.playback_status = Status.IDLE
                            self.agent_status = Status.PROCESSING
                            self.interruption_status = InterruptionStatus.IDLE
                            self.response_in_progress = False
                            self.current_generation_id += 1
                            self.client_playback_was_active_before_interruption = False
                            
                            print(f"    [LLM Task] 🔄 Processing pending chat history (generation_id={self.current_generation_id})")
                            
                            # Log the chat history being used
                            print("\n" + "="*60)
                            print("    [LLM Task] 🤖 PROCESSING PENDING CHAT HISTORY:")
                            print("="*60)
                            print(f"    Chat History Length: {len(self.chat_history)} messages")
                            for i, msg in enumerate(self.chat_history):
                                role = msg.get('role', 'unknown')
                                content = msg.get('content', '')
                                print(f"    [{i+1}] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")
                            print("="*60 + "\n")
                            
                            # Process chat history (no new user input - just process existing history)
                            self.llm_task_handle = asyncio.create_task(
                                self.run_agent_flow(self.chat_history)
                            )
                            
                            print("    [LLM Task] ✅ Agent started processing pending chat history.")
                            return
                    
                    # If we get here, we have a false alarm but:
                    # - No playback to resume
                    # - No pending chat history to process
                    # - Just reset interruption status
                    print("    [LLM Task] 💤 False alarm detected but nothing to resume/process")
                    print("    [LLM Task]    Resetting interruption status...")
                    self.client_playback_was_active_before_interruption = False
                    self.interruption_status = InterruptionStatus.IDLE
                    print("    [LLM Task] ✅ Interruption status reset.")
                    return
            
            else:
                # --- PATH B: TRUE INTERRUPTION / NEW TURN (Regenerate) ---
                print(f"    [LLM Task] New prompt: '{user_prompt}' - Regenerating response")
                
                # 1. Stop all old work
                await self._ensure_playback_paused(
                    reason="Pausing playback before regenerating response",
                    force_notify=False
                )
                self.ai_agent.cancel()  # Cancels LLM + Tools
                
                # 2. Clear old audio immediately
                self.audio_output_queue.clear()
                
                # 3. Update Chat History with the user prompt
                # For interruptions: cleaned_history already has the new text appended to last user message
                # For new turns: we need to add a new user message
                if not is_interruption:
                    # New turn - add new user message
                    self.chat_history.append({"role": "user", "content": user_prompt})
                
                # 4. Reset states for new response
                # Set playback to IDLE so AudioPlaybackWorker can auto-activate on new audio
                self.playback_status = Status.IDLE
                self.agent_status = Status.PROCESSING
                self.interruption_status = InterruptionStatus.IDLE  # Reset interruption before starting new flow
                self.response_in_progress = False  # Reset - will be set to True when agent starts
                self.current_generation_id += 1  # Increment generation ID for new response
                print(f"    [LLM Task] States reset: playback=IDLE, agent=PROCESSING, interruption=IDLE, response_in_progress=False, generation_id={self.current_generation_id}")
                
                # 5. Log the full prompt being sent to agent
                print("\n" + "="*60)
                print("    [LLM Task] 🤖 CALLING AGENT WITH PROMPT:")
                print("="*60)
                print(f"    Chat History Length: {len(self.chat_history)} messages")
                for i, msg in enumerate(self.chat_history):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    print(f"    [{i+1}] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")
                print("="*60 + "\n")
                
                # 6. Call Agent (streams to text_stream_queue) asynchronously
                self.llm_task_handle = asyncio.create_task(
                    self.run_agent_flow(self.chat_history)
                )
        
        except asyncio.CancelledError:
            print("    [LLM Task] Cancelled during processing.")
        except Exception as e:
            print(f"    [LLM Task] ERROR: {e}")
            self.agent_status = Status.IDLE
    
    async def run_agent_flow(self, chat_history_for_agent: List[Dict[str, str]]):
        """
        Run the Agent (LLM) flow - streams text to text_stream_queue.
        
        This is decoupled from TTS - agent produces text, TTS worker consumes it.
        Text is batched into complete sentences to prevent overlapping audio.
        
        Args:
            chat_history_for_agent: Chat history to send to the agent
        """
        try:
            # Mark that we're in a response cycle
            self.response_in_progress = True
            print("\n[Agent Flow] ▶️ Response cycle started (response_in_progress = True)")
            print(f"[Agent Flow] Received {len(chat_history_for_agent)} messages in chat_history")
            
            # Reset partial tracking for this run
            self.agent_streamed_text_so_far = ""
            self.agent_message_committed = False
            
            # Get the text stream from the agent
            print("[Agent Flow] 🔄 Calling AI Agent...")
            text_stream = self.ai_agent.generate_response(chat_history_for_agent)
            
            final_agent_response = ""
            first_chunk_received = False
            
            # Buffer for batching text into sentences
            text_buffer = ""
            sentence_delimiters = {'.', '!', '?', '\n'}
            
            async for text_chunk in text_stream:
                if text_chunk is None:  # End of stream
                    break
                
                if not first_chunk_received:
                    # Agent started streaming
                    self.agent_status = Status.STREAMING
                    first_chunk_received = True
                
                # Track the partial text as soon as it is streamed
                final_agent_response += text_chunk
                self.agent_streamed_text_so_far += text_chunk
                
                # Add to buffer
                text_buffer += text_chunk
                
                # Check if we have a complete sentence
                if any(delimiter in text_chunk for delimiter in sentence_delimiters):
                    # Send the complete sentence to TTS
                    if text_buffer.strip():
                        await self.text_stream_queue.put(text_buffer)
                        print(f"    [Agent Flow] Sending sentence to TTS: '{text_buffer.strip()[:50]}...'")
                        text_buffer = ""
            
            # Send any remaining text in buffer
            if text_buffer.strip():
                await self.text_stream_queue.put(text_buffer)
                print(f"    [Agent Flow] Sending final text to TTS: '{text_buffer.strip()[:50]}...'")
            
            # Signal end-of-stream to TTS worker
            await self.text_stream_queue.put(None)
            
            # Add agent's full response to history if we finished cleanly
            if final_agent_response.strip():
                self.chat_history.append({"role": "agent", "content": final_agent_response})
                self.agent_message_committed = True
                print("    [Agent Flow] ✅ Appended agent response to history.")
                print(f"    [Agent Flow] Response: '{final_agent_response[:100]}{'...' if len(final_agent_response) > 100 else ''}'")
            
            self.agent_status = Status.IDLE
            print("    [Agent Flow] ✅ Complete (agent_status = IDLE).")
        
        except asyncio.CancelledError:
            print("    [Agent Flow] ❌ Cancelled (interrupted).")
            self.agent_status = Status.IDLE
        except Exception as e:
            print(f"    [Agent Flow] ❌ ERROR: {e}")
            self.agent_status = Status.IDLE
    
    
    async def tts_worker(self):
        """
        TTS Worker - consumes text from text_stream_queue and produces audio.
        
        This runs continuously in the background, waiting for text chunks.
        """
        print("      [TTS Worker] Started. Waiting for text...")
        while True:
            try:
                # Wait for text chunk from agent
                text_chunk = await self.text_stream_queue.get()
                
                # Check for end-of-stream
                if text_chunk is None:
                    print("      [TTS Worker] End of stream signal received.")
                    # Signal end to playback worker
                    # The AudioPlaybackWorker will set playback_status to IDLE when done
                    await self.audio_output_queue.put(None)
                    self.tts_status = Status.IDLE
                    continue
                
                # Set TTS status if not already processing
                if self.tts_status == Status.IDLE:
                    self.tts_status = Status.PROCESSING
                
                # Generate audio for this text chunk
                try:
                    b64_audio_string = await text_to_speech_base64(text_chunk)
                    if b64_audio_string:
                        # Put audio into playback queue
                        # AudioPlaybackWorker will automatically set status to ACTIVE
                        await self.audio_output_queue.put({"audio": b64_audio_string})
                        print(f"      [TTS Worker] Generated audio for: '{text_chunk[:30]}...'")
                
                except TTSError as e:
                    print(f"      [TTS Worker] ERROR: {e}")
                    # Continue processing next chunks even if one fails
                
                self.text_stream_queue.task_done()
            
            except asyncio.CancelledError:
                print("      [TTS Worker] Shutting down...")
                self.tts_status = Status.IDLE
                break
            except Exception as e:
                print(f"      [TTS Worker] ERROR: {e}")
                self.tts_status = Status.IDLE

