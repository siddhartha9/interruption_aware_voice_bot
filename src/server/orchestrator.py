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
        
        # Save client playback state (for potential false alarm resume later)
        client_was_playing = self.client_playback_active
        self.client_playback_was_active_before_interruption = client_was_playing
        print(f"[Orchestrator] Saved client playback state: {self.client_playback_was_active_before_interruption}")
        
        # Immediately notify client to pause (for instant UX feedback)
        # But don't cancel agent or clear queues yet - llm_processing_task() will handle that
        # 
        # BUG FIX: Always set playback_status to PAUSED during interruption, even if playback
        # hasn't started yet (e.g., during response generation). This ensures the resume logic
        # in llm_processing_task can properly detect false alarms vs real interruptions.
        if self.client_playback_active or self.playback_status == Status.ACTIVE:
            await self.websocket.send_json({"event": "stop_playback"})
            print(f"[Orchestrator] ⏸️  Sent stop_playback to client (instant feedback)")
        
        # Always mark as PAUSED to enable false alarm detection later
        self.playback_status = Status.PAUSED
        print(f"[Orchestrator] ⏸️  Playback status set to PAUSED")
        
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
        
        Simplified flow:
        1. Get STT output & check for interruption
        2. Generate prompt (returns True/False for new prompt needed)
        3. CASE 1: Resume if no new prompt needed AND playback paused
        4. CASE 2: Otherwise, regenerate response
        """
        try:
            # 1. Debounce/Coalesce
            print("    [LLM Task] Triggered. Debouncing...")
            await asyncio.sleep(0.1)  # 100ms debounce
        except asyncio.CancelledError:
            print("    [LLM Task] Debounce cancelled.")
            return
        
        try:
            # 2. ALWAYS stop all ongoing work and clear queues
            # This ensures we start with a clean slate for decision-making
            print(f"    [LLM Task] Current agent status: {self.agent_status}")
            
            # 1. Cancel AI Agent (LLM generation)
            print("    [LLM Task] Cancelling AI Agent...")
            self.ai_agent.cancel()  # This also cancels all active tool calls via ActiveToolRegistry
            
            # 2. Cancel Tool Calls - handled automatically by ai_agent.cancel()
            # The cancel() above triggers all registered tools to stop via ActiveToolRegistry
            
            # 3. Cancel TTS - we don't have explicit TTS cancel, but clearing queues stops processing
            # TTS worker will finish current synthesis but won't process new queued items
            
            # 4. Clear Text Stream Queue
            while not self.text_stream_queue.empty():
                try:
                    self.text_stream_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                            
            # 5. Clear Audio Queue
            self.audio_output_queue.clear()
            
            print("    [LLM Task] ✅ Stopped: Agent + Tools + TTS | Cleared: Text Queue + Audio Queue")
            
            # Step 1: Get STT output (might be empty - that's OK for false alarms)
            stt_transcript = self.stt_output_list.copy() if self.stt_output_list else []
            has_stt_output = len(stt_transcript) > 0
            
            # Step 2: Check if interruption is ACTIVE
            is_interruption_active = (self.interruption_status == InterruptionStatus.ACTIVE)
            
            # Step 3: Ask Prompt Generator if new prompt is needed
            is_new_prompt_needed, modified_user_prompt, cleaned_history = self.prompt_generator.generate_prompt(
                stt_output_list=stt_transcript,
                chat_history=self.chat_history,
                is_interruption=is_interruption_active
            )
            
            # Clear STT list after consuming
            self.stt_output_list.clear()
            
            # Log current state
            print(f"    [LLM Task] State:")
            print(f"      has_stt_output: {has_stt_output}")
            print(f"      is_new_prompt_needed: {is_new_prompt_needed}")
            print(f"      is_interruption_active: {is_interruption_active}")
            print(f"      playback_status: {self.playback_status}")
            print(f"      agent_status: {self.agent_status}")
            print(f"      modified_user_prompt: '{modified_user_prompt}'")
            
            # ========================================================================
            # CASE 1: Resume Audio (no new prompt needed AND playback was paused)
            # ========================================================================
            # Conditions: 
            # - (No STT output OR STT has output but new prompt not needed) 
            # - AND playback is paused
            # Action: Resume audio and return
            # ========================================================================
            
            should_resume = (not has_stt_output or not is_new_prompt_needed) and (self.playback_status == Status.PAUSED)
            
            if should_resume:
                print("    [LLM Task] 📢 CASE 1: Resume Audio")
                print(f"    [LLM Task]   Reason: {'No STT output' if not has_stt_output else 'False alarm / confirmation'}")
                
                # Send resume event to client
                await self.websocket.send_json({"event": "playback_resume"})
                print("    [LLM Task] ✅ Sent playback_resume to client")
                
                # BUG FIX: Don't check audio_output_queue (we just cleared it at line 618!)
                # Instead, trust that we're resuming from PAUSED state, which means there
                # was playback happening before. Set to ACTIVE so client can resume its local queue.
                # If client has no audio, it will naturally stop and send playback_ended.
                self.playback_status = Status.ACTIVE
                self.client_playback_active = True
                print("    [LLM Task] ✅ Server playback ACTIVE (resuming from PAUSED)")
                
                # Reset interruption state
                self.client_playback_was_active_before_interruption = False
                self.interruption_status = InterruptionStatus.IDLE
                print("    [LLM Task] ✅ Interruption reset. CASE 1 complete.")
                return
                
            # ========================================================================
            # CASE 2: Regenerate Response (anything else)
            # ========================================================================
            # Conditions: New prompt needed OR no paused playback to resume
            # Actions:
            # 1. Clear audio output stream
            # 2. Put playback on listening mode (IDLE)
            # 3. Modify chat history based on STT output
            # 4. Set interruption to IDLE
            # 5. Run agent → text chunks → TTS queue → playback
            # ========================================================================
            
            print("    [LLM Task] 🔄 CASE 2: Regenerate Response")
            
            # Step 1: Ensure playback is paused (queues already cleared at top of function)
            await self._ensure_playback_paused(
                reason="Preparing for new response",
                force_notify=False
            )
            
            # Step 2: Set playback to listening mode (IDLE)
            self.playback_status = Status.IDLE
            
            # Step 3: Modify chat history
            if not has_stt_output or not is_new_prompt_needed:
                # Use same chat history (false alarm with no paused playback, or pending history)
                print("    [LLM Task] Using existing chat history (no new user input)")
                self.chat_history = cleaned_history
            else:
                # New user input - modify history
                print(f"    [LLM Task] Modifying chat history with new prompt: '{modified_user_prompt}'")
                
                # If agent has last message, check if we should remove it (interrupted response)
                if len(cleaned_history) > 0 and cleaned_history[-1].get("role") == "agent":
                    if is_interruption_active:
                        # Remove interrupted agent response
                        cleaned_history = cleaned_history[:-1]
                        print("    [LLM Task] Removed interrupted agent response")
                
                # Replace or append user message
                if len(cleaned_history) > 0 and cleaned_history[-1].get("role") == "user":
                    # Replace last user message with modified prompt
                    cleaned_history[-1]["content"] = modified_user_prompt
                    print("    [LLM Task] Replaced last user message")
                else:
                    # Append new user message
                    cleaned_history.append({"role": "user", "content": modified_user_prompt})
                    print("    [LLM Task] Appended new user message")
                
                self.chat_history = cleaned_history
            
            # Step 4: Set interruption to IDLE and reset states
            self.interruption_status = InterruptionStatus.IDLE
            self.client_playback_was_active_before_interruption = False
            self.agent_status = Status.PROCESSING
            self.response_in_progress = False
            self.current_generation_id += 1
            
            print(f"    [LLM Task] States reset: generation_id={self.current_generation_id}")
            
            # Step 5: Log chat history and run agent
            print("\n" + "="*60)
            print("    [LLM Task] 🤖 CALLING AGENT:")
            print("="*60)
            print(f"    Chat History Length: {len(self.chat_history)} messages")
            for i, msg in enumerate(self.chat_history):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                print(f"    [{i+1}] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")
            print("="*60 + "\n")
                
            # Run agent flow (agent → text_stream_queue → TTS → audio_output_queue → playback)
            # Tools register themselves in active_tool_registry during execution
            # Sync tools: agent stays in PROCESSING
            # Async tools: agent returns but tool stays registered until complete
            self.llm_task_handle = asyncio.create_task(
                    self.run_agent_flow(self.chat_history)
                )
            
            print("    [LLM Task] ✅ CASE 2 complete. Agent flow started.")
        
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

