"""
This is the "brain" of our application.
It holds all the state, manages all the queues,
and runs all the background workers.
"""


import asyncio
from enum import Enum
import time
from typing import List, Optional


# Import our stateless tools
# Note: These imports assume the modules exist in the same directory
# If module files don't exist yet, they need to be created
try:
    from vad import VADProcessor, VADEvent
except ImportError:
    # Fallback if the modules use numeric prefixes
    try:
        import importlib
        vad_module = importlib.import_module('3_vad')
        VADProcessor = vad_module.VADProcessor
        VADEvent = vad_module.VADEvent
    except ImportError:
        print("Warning: VAD module not found")
        VADProcessor = None
        VADEvent = None

try:
    from stt import STTProcessor
except ImportError:
    try:
        import importlib
        stt_module = importlib.import_module('4_stt')
        STTProcessor = stt_module.STTProcessor
    except ImportError:
        print("Warning: STT module not found")
        STTProcessor = None

try:
    from ai_agent import AIAgent
except ImportError:
    try:
        import importlib
        agent_module = importlib.import_module('5_ai_agent')
        AIAgent = agent_module.AIAgent
    except ImportError:
        print("Warning: AI Agent module not found")
        AIAgent = None

try:
    from tts import TTSError, text_to_speech_base64
except ImportError:
    try:
        import importlib
        tts_module = importlib.import_module('6_tts')
        TTSError = tts_module.TTSError
        text_to_speech_base64 = tts_module.text_to_speech_base64
    except ImportError:
        print("Warning: TTS module not found")
        TTSError = Exception
        text_to_speech_base64 = None


# --- 1. State Definitions ---


class Status(Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    STREAMING = "STREAMING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"


class InterruptionStatus(Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING" # The "lock" state
    ACTIVE = "ACTIVE"      # The "flag" state


# --- 2. The Orchestrator Class ---


class ConnectionOrchestrator:
    """
    Manages the state and logic for a single WebSocket connection.
    """
    
    def __init__(self, websocket):
        print("[Orchestrator] Initializing new connection...")
        self.websocket = websocket
        
        # --- State Variables ---
        self.stt_status = Status.IDLE
        self.agent_status = Status.IDLE
        self.tts_status = Status.IDLE
        self.tool_status = Status.IDLE
        self.playback_status = Status.IDLE
        self.interruption_status = InterruptionStatus.IDLE
        
        # --- Data Queues & Lists ---
        self.stt_job_queue = asyncio.Queue()
        self.stt_output_list = []
        self.audio_output_queue = asyncio.Queue(maxsize=20) # Buffer for 20 audio chunks
        self.chat_history = []
        
        # --- Background Task Handles ---
        self.llm_task_handle: Optional[asyncio.Task] = None
        self.stt_worker_handle: Optional[asyncio.Task] = None
        self.playback_worker_handle: Optional[asyncio.Task] = None
        
        # --- VAD & Audio Buffering ---
        self.vad_processor = VADProcessor(aggressiveness=3)
        self.current_audio_buffer = bytearray()
        
        # --- Stateless Tool Initialization ---
        self.stt_processor = STTProcessor()
        self.ai_agent = AIAgent()
        
        # --- Agent partial stream tracking (for interruptions) ---
        self.agent_streamed_text_so_far = ""
        self.agent_message_committed = False
        
    def is_system_idle(self):
        """Checks if the system is completely at rest."""
        return (self.stt_status == Status.IDLE and
                self.agent_status == Status.IDLE and
                self.tts_status == Status.IDLE and
                self.tool_status == Status.IDLE and
                self.playback_status == Status.IDLE)
                
    async def start_workers(self):
        """Starts the long-running background tasks for this connection."""
        print("[Orchestrator] Starting background workers...")
        self.stt_worker_handle = asyncio.create_task(self.stt_worker())
        self.playback_worker_handle = asyncio.create_task(self.playback_worker())
        # Note: llm_processing_task is triggered by stt_worker, not run in a loop


    async def cleanup(self):
        """Cancels all background tasks on disconnect."""
        print("[Orchestrator] Cleaning up connection...")
        if self.stt_worker_handle:
            self.stt_worker_handle.cancel()
        if self.playback_worker_handle:
            self.playback_worker_handle.cancel()
        if self.llm_task_handle and not self.llm_task_handle.done():
            self.llm_task_handle.cancel()
        self.ai_agent.cancel() # Cancel any in-flight LangGraph/tool jobs

    def clear_audio_output_queue(self):
        """Helper to quickly clear the audio output queue."""
        while not self.audio_output_queue.empty():
            try:
                self.audio_output_queue.get_nowait()
            except Exception:
                break

    # --- 3. VAD & Event Triggers ---


    async def process_audio_chunk(self, chunk: bytes):
        """
        This is the main entry point for raw audio.
        It runs the VAD and triggers Event 1 and Event 2.
        """
        vad_event = self.vad_processor.process_chunk(chunk)
        
        if vad_event == VADEvent.START:
            await self.on_user_starts_speaking()
            self.current_audio_buffer.extend(chunk)
            
        elif vad_event == VADEvent.SPEECH:
            self.current_audio_buffer.extend(chunk)
            
        elif vad_event == VADEvent.END:
            # --- EVENT 2: User Ends Speaking ---
            self.current_audio_buffer.extend(chunk)
            await self.on_user_ends_speaking(bytes(self.current_audio_buffer))
            self.current_audio_buffer.clear()


    async def on_user_starts_speaking(self):
        """
        Event 1: The "Pause" Reaction.
        Reacts immediately to user speech.
        """
        print("\n--- EVENT 1: User Starts Speaking ---")
        
        # If the system is idle, it's a new turn. Do nothing.
        if self.is_system_idle():
            print("[Orchestrator] System is IDLE. This is a new turn.")
            return


        # --- If we are here, this is a TRUE interruption ---


        # Only act if playback is currently active
        if self.playback_status == Status.ACTIVE:
            print("[Orchestrator] INTERRUPT: Playback is ACTIVE. Pausing.")
            
            # Lock: Set state to "Processing"
            self.interruption_status = InterruptionStatus.PROCESSING


            # Run Pause Logic
            self.playback_status = Status.PAUSED
            
            # Send pause command to client
            await self.websocket.send_json({"event": "playback_pause"})
            print("[Orchestrator] Playback set to PAUSED.")


            # Unlock: Mark that an interruption has been handled
            self.interruption_status = InterruptionStatus.ACTIVE


    async def on_user_ends_speaking(self, complete_audio_buffer: bytes):
        """
        Event 2: The "Audio Producer".
        Adds the user's completed audio to the STT job queue.
        """
        print(f"\n--- EVENT 2: User Ends Speaking (Buffer: {len(complete_audio_buffer)} bytes) ---")
        
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
                        # to restart the debounce timer.
                        self.llm_task_handle.cancel()
                    self.llm_task_handle = asyncio.create_task(self.llm_processing_task())
                else:
                    print("  [STT Worker] STT returned no text.")
                
                self.stt_job_queue.task_done()
                
            except asyncio.CancelledError:
                print("  [STT Worker] Shutting down...")
                break
            except Exception as e:
                print(f"  [STT Worker] ERROR: {e}")
                self.stt_status = Status.IDLE
                # Continue to the next job
                
    async def llm_processing_task(self):
        """
        Worker: The "Decision Maker".
        Runs after being triggered (with a debounce), "batches" all new
        text summaries, and decides whether to resume or regenerate.
        """
        
        try:
            # 1. Debounce/Coalesce
            print("    [LLM Task] Triggered. Debouncing...")
            await asyncio.sleep(0.1) # 100ms debounce
        except asyncio.CancelledError:
            print("    [LLM Task] Debounce cancelled.")
            return # A new speech event came in, cancel this task


        try:
            # 2. Check if Busy
            if self.agent_status in (Status.PROCESSING, Status.STREAMING):
                print("    [LLM Task] Agent is busy. Will let current run finish.")
                return 


            print("    [LLM Task] Starting LLM processing...")
            
            # 3. Handle Interruption & Prompt Modification
            if self.interruption_status == InterruptionStatus.PROCESSING:
                print("    [LLM Task] Waiting for interruption lock...")
                await asyncio.sleep(0.05) # Wait for lock to clear


            if not self.stt_output_list:
                print("    [LLM Task] No text to process.")
                return


            # --- Prompt Modifier Logic ---
            is_new_prompt_needed = True
            
            # Consume all text in the list
            all_new_text = " ".join(self.stt_output_list)
            self.stt_output_list.clear() # We have consumed the text
            
            users_last_message = None
            
            if self.interruption_status == InterruptionStatus.ACTIVE:
                # 1. Clean up Agent's partial response
                if self.chat_history and self.chat_history[-1]["role"] == "agent":
                    print(f"    [Chat History] Interruption. Popping last agent message: '{self.chat_history[-1]['content'][:20]}...'")
                    self.chat_history.pop()
                
                # 2. Get the *actual* last user message
                if self.chat_history and self.chat_history[-1]["role"] == "user":
                    users_last_message = self.chat_history[-1]["content"]


                # 3. Decide if new prompt is needed
                if "uh huh" in all_new_text.lower() or "okay" in all_new_text.lower():
                    is_new_prompt_needed = False
            
            # 4. --- THE DECISION ---
            if not is_new_prompt_needed and self.playback_status == Status.PAUSED:
                # --- PATH A: FALSE ALARM (Resume) ---
                print("    [LLM Task] DECISION: Resume playback.")
                self.playback_status = Status.ACTIVE
                await self.websocket.send_json({"event": "playback_resume"})
                self.interruption_status = InterruptionStatus.IDLE # Reset
                return


            else:
                # --- PATH B: TRUE INTERRUPTION / NEW TURN (Regenerate) ---
                print("    [LLM Task] DECISION: Regenerate response.")
                
                # 1. Stop all old work
                self.ai_agent.cancel()  # Cancels LLM + Tools
                
                # 2. Commit partial agent stream (only what has been streamed so far)
                if self.agent_streamed_text_so_far.strip() and not self.agent_message_committed:
                    self.chat_history.append({
                        "role": "agent",
                        "content": self.agent_streamed_text_so_far
                    })
                    self.agent_message_committed = True  # avoid duplicate commits
                
                # 3. Clear old audio immediately
                self.clear_audio_output_queue()
                
                # 4. Update Chat History for the new user input
                # Always add a new user message for the interruption content (or new turn)
                self.chat_history.append({"role": "user", "content": all_new_text})
                
                # 5. Set agent state
                self.playback_status = Status.IDLE
                self.agent_status = Status.PROCESSING
                
                # 6. Call Agent (LLM -> TTS -> Playback) asynchronously
                self.llm_task_handle = asyncio.create_task(
                    self.run_agent_and_tts_flow(self.chat_history)
                )


            self.interruption_status = InterruptionStatus.IDLE
            
        except asyncio.CancelledError:
            print("    [LLM Task] Cancelled during processing.")
        except Exception as e:
            print(f"    [LLM Task] ERROR: {e}")
            self.agent_status = Status.IDLE


    async def run_agent_and_tts_flow(self, chat_history_for_agent):
        """
        Helper to run the full LLM-TTS-Playback chain.
        This function is called by llm_processing_task.
        """
        try:
            # Reset partial tracking for this run
            self.agent_streamed_text_so_far = ""
            self.agent_message_committed = False

            # 1. Get the text stream queue from the agent
            text_stream_queue = self.ai_agent.generate_response(chat_history_for_agent)
            
            # 2. Start the TTS task, reading from the queue
            self.tts_status = Status.PROCESSING
            
            final_agent_response = ""
            first_chunk_received = False
            
            async for text_chunk in text_stream_queue:
                if text_chunk is None:  # End of stream
                    break
                
                if not first_chunk_received:
                    # This is the "time to first audio"
                    self.agent_status = Status.STREAMING
                    first_chunk_received = True

                # Track the partial text as soon as it is streamed
                final_agent_response += text_chunk
                self.agent_streamed_text_so_far += text_chunk
                
                # Generate audio for non-empty chunks
                if text_chunk.strip():
                    try:
                        b64_audio_string = await text_to_speech_base64(text_chunk)
                        if b64_audio_string:
                            # Ensure playback becomes ACTIVE so playback_worker consumes the queue
                            if self.playback_status == Status.IDLE:
                                self.playback_status = Status.ACTIVE
                            await self.audio_output_queue.put({"audio": b64_audio_string})
                    except TTSError as e:
                        print(f"      [TTS] ERROR: {e}")
                        # Continue streaming text even if a TTS chunk fails
            
            # Signal end-of-stream to playback
            await self.audio_output_queue.put(None)
            
            # Add agent's full response to history if we finished cleanly
            if final_agent_response.strip():
                self.chat_history.append({"role": "agent", "content": final_agent_response})
                self.agent_message_committed = True
                print("    [Chat History] Appended agent response.")
            
            self.tts_status = Status.IDLE
            self.agent_status = Status.IDLE  # LLM/TTS flow is done

        except asyncio.CancelledError:
            print(f"    [Agent/TTS Flow] was cancelled.")
            self.agent_status = Status.IDLE
            self.tts_status = Status.IDLE
        except Exception as e:
            print(f"    [Agent/TTS Flow] ERROR: {e}")
            self.agent_status = Status.IDLE
            self.tts_status = Status.IDLE


    async def playback_worker(self):
        """
        Worker: The "Audio Consumer".
        Runs in a loop, playing audio from the output queue.
        """
        print("        [Playback Worker] Started. Waiting for audio.")
        while True:
            try:
                if self.playback_status == Status.IDLE or self.playback_status == Status.PAUSED:
                    await asyncio.sleep(0.05) # Sleep briefly
                    continue
                
                # --- Playback is ACTIVE ---
                try:
                    # 1. Get next chunk
                    item = await asyncio.wait_for(self.audio_output_queue.get(), timeout=0.1)
                    
                    # 2. Check for end-of-stream
                    if item is None:
                        print("        [Playback] End of stream. Setting to IDLE.")
                        self.playback_status = Status.IDLE
                        continue


                    # 3. We have a valid chunk
                    b64_audio_string = item["audio"]
                    print(f"        [Playback] SENDING: Audio chunk (Base64)...")
                    
                    # 4. Send to client for playback
                    await self.websocket.send_json({
                        "event": "play_audio",
                        "audio": b64_audio_string,
                    })
                    
                    self.audio_output_queue.task_done()


                except asyncio.TimeoutError:
                    # Queue was empty, but we are still ACTIVE.
                    # Check if the upstream processes are done.
                    if self.tts_status == Status.IDLE and self.agent_status == Status.IDLE:
                        print("        [Playback] TTS/Agent is IDLE and queue is empty. Finishing.")
                        self.playback_status = Status.IDLE
                    pass # Just loop again, still ACTIVE


            except asyncio.CancelledError:
                print("        [Playback Worker] Shutting down...")
                break
            except Exception as e:
                print(f"        [Playback Worker] ERROR: {e}")
                self.playback_status = Status.IDLE
                # Don't break the loop, try to recover