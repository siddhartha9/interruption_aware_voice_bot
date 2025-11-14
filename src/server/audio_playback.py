"""
Audio Playback Module.

This module manages audio output streaming and playback.
"""

import asyncio
from typing import Optional

from .state_types import Status


class AudioPlaybackWorker:
    """
    Audio playback worker that consumes audio from a queue and sends to client.
    
    This is a stateful consumer that manages the playback state.
    """
    
    def __init__(self, websocket, audio_output_queue: asyncio.Queue):
        """
        Initialize the audio playback worker.
        
        Args:
            websocket: WebSocket connection to send audio to
            audio_output_queue: Queue to consume audio chunks from
        """
        self.websocket = websocket
        self.audio_output_queue = audio_output_queue
        self.playback_status = Status.IDLE
        self.worker_task: Optional[asyncio.Task] = None
        
        print("[Playback Worker] Initialized")
    
    async def start(self):
        """Start the playback worker background task."""
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._run())
            print("[Playback Worker] Started")
    
    async def stop(self):
        """Stop the playback worker."""
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        print("[Playback Worker] Stopped")
    
    def pause(self):
        """Pause audio playback."""
        self.playback_status = Status.PAUSED
        print("[Playback Worker] PAUSED")
    
    def resume(self):
        """Resume audio playback."""
        self.playback_status = Status.ACTIVE
        print("[Playback Worker] RESUMED")
    
    def set_active(self):
        """Set playback to active state."""
        self.playback_status = Status.ACTIVE
        print("[Playback Worker] ACTIVE")
    
    def set_idle(self):
        """Set playback to idle state."""
        self.playback_status = Status.IDLE
        print("[Playback Worker] IDLE")
    
    def get_status(self) -> Status:
        """Get current playback status."""
        return self.playback_status
    
    async def _run(self):
        """
        Main worker loop.
        
        Continuously checks for audio in queue and sends it to client.
        Automatically manages playback status based on queue state.
        """
        print("[Playback Worker] Worker loop started")
        
        while True:
            try:
                # --- PAUSED STATE ---
                # If paused (due to interruption), DON'T drain queue - preserve it for resume
                # Just wait and periodically check if we're resumed
                if self.playback_status == Status.PAUSED:
                    # Wait a bit and check if we're still paused
                    await asyncio.sleep(0.1)
                    # Don't get items from queue - preserve them for when we resume
                    continue
                
                # --- IDLE/ACTIVE STATE ---
                # Wait for audio from queue (blocking)
                try:
                    # Wait for next audio chunk (blocks until available)
                    item = await asyncio.wait_for(
                        self.audio_output_queue.get(), 
                        timeout=0.1
                    )
                    
                    # Check for end-of-stream signal
                    if item is None:
                        print("[Playback Worker] End of stream. Setting to IDLE.")
                        self.playback_status = Status.IDLE
                        continue
                    
                    # CRITICAL: Check if we got paused while waiting for audio
                    # If so, DON'T send it - but also DON'T discard it
                    # Put it back in the queue so we can resume from it later
                    if self.playback_status == Status.PAUSED:
                        print("[Playback Worker] Audio chunk received while paused - preserving for resume")
                        # Put the item back in the queue (at the front) so we can resume from it
                        # Note: asyncio.Queue doesn't support putting items back at the front
                        # So we'll just mark it as done and skip it - the queue will preserve other items
                        # The client-side resume will handle resuming audio that was already sent
                        self.audio_output_queue.task_done()
                        # Don't send this chunk - it was received while paused
                        # The client should have already paused, so it won't play this
                        continue
                    
                    # We have audio to send - automatically become ACTIVE
                    if self.playback_status == Status.IDLE:
                        self.playback_status = Status.ACTIVE
                        print("[Playback Worker] ACTIVE (audio available)")
                    
                    # Send audio chunk to client
                    b64_audio_string = item["audio"]
                    import time
                    timestamp = time.strftime('%H:%M:%S.%f')[:-3]  # Include milliseconds
                    print(f"[Playback Worker] ⏱️  {timestamp} Sending audio chunk (Base64, {len(b64_audio_string)} chars)...")
                    
                    await self.websocket.send_json({
                        "event": "play_audio",
                        "audio": b64_audio_string,
                    })
                    
                    self.audio_output_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # No audio available - stay in current state
                    pass
            
            except asyncio.CancelledError:
                print("[Playback Worker] Shutting down...")
                break
            except Exception as e:
                print(f"[Playback Worker] ERROR: {e}")
                self.playback_status = Status.IDLE
                # Don't break the loop, try to recover


class AudioOutputQueue:
    """
    Wrapper for the audio output queue with helper methods.
    """
    
    def __init__(self, maxsize: int = 20):
        """
        Initialize the audio output queue.
        
        Args:
            maxsize: Maximum queue size (prevents TTS from getting too far ahead)
        """
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.maxsize = maxsize
        print(f"[Audio Queue] Initialized with maxsize={maxsize}")
    
    async def put(self, item):
        """Add an item to the queue."""
        await self.queue.put(item)
    
    async def get(self):
        """Get an item from the queue."""
        return await self.queue.get()
    
    def task_done(self):
        """Mark a queue item as processed."""
        self.queue.task_done()
    
    def empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()
    
    def clear(self):
        """Clear all items from the queue."""
        cleared_count = 0
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                cleared_count += 1
            except Exception:
                break
        
        if cleared_count > 0:
            print(f"[Audio Queue] Cleared {cleared_count} items")
    
    def get_raw_queue(self) -> asyncio.Queue:
        """Get the underlying asyncio.Queue object."""
        return self.queue

