"""
Interruption Handler Module.

This module manages interruption detection and decision-making logic.
Focuses on interruption-specific state management and actions.
"""

import asyncio
from typing import List, Dict, Optional, Tuple

from .state_types import Status, InterruptionStatus
from .active_tool_registry import get_active_tool_registry


class InterruptionHandler:
    """
    Handles interruption logic and decision-making.
    
    This module contains the "pause-and-decide" strategy for handling
    user interruptions (barge-in) during agent speech.
    
    NOTE: Prompt generation has been moved to the Orchestrator for better
    separation of concerns. This handler focuses only on interruption actions.
    """
    
    def __init__(self):
        """Initialize the interruption handler."""
        self.interruption_status = InterruptionStatus.IDLE
        print("[Interruption Handler] Initialized")
    
    def get_status(self) -> InterruptionStatus:
        """Get current interruption status."""
        return self.interruption_status
    
    def set_status(self, status: InterruptionStatus):
        """Set interruption status."""
        self.interruption_status = status
    
    def reset(self):
        """Reset interruption status to IDLE."""
        self.interruption_status = InterruptionStatus.IDLE
    
    async def handle_user_starts_speaking(
        self, 
        agent_status: Status,
        ai_agent,
        text_stream_queue,
        audio_output_queue
    ) -> tuple[InterruptionStatus, bool]:
        """
        Handle Event 1: User Starts Speaking (The "Pause" Reaction).
        
        This is called immediately when the client detects user starting to speak.
        
        Logic:
            - If agent is PROCESSING/STREAMING -> Cancel agent & clear queues
            - Note: Playback pause is handled by client-side VAD immediately
        
        Args:
            agent_status: Current agent status
            ai_agent: AI agent instance (to cancel)
            text_stream_queue: Text stream queue (Agent → TTS)
            audio_output_queue: Audio queue (TTS → Playback)
            
        Returns:
            Tuple of (new_interruption_status, agent_was_cancelled)
        """
        print("\n--- EVENT 1: User Starts Speaking ---")
            
            # Lock: Set state to "Processing"
        self.interruption_status = InterruptionStatus.PROCESSING
            
        agent_was_cancelled = False
        
        # 1. Clear text queue immediately (prevents TTS from generating more audio from stale text)
        # Note: We DON'T clear audio queue here - we pause instead (in case it's a false alarm)
        # The audio queue will be cleared later if it's a true interruption
        cleared_text_count = 0
        while not text_stream_queue.empty():
            try:
                text_stream_queue.get_nowait()
                cleared_text_count += 1
            except:
                break
        if cleared_text_count > 0:
            print(f"[Interruption Handler] Text queue cleared ({cleared_text_count} chunks discarded).")
        
        # Note: Audio queue is NOT cleared here - we pause playback instead
        # If it's a false alarm, we can resume from the existing audio queue
        # If it's a true interruption, the audio queue will be cleared in llm_processing_task
        print("[Interruption Handler] Audio queue preserved (paused, not cleared - may resume on false alarm).")
        
        # 2. Cancel all active tool executions
        registry = get_active_tool_registry()
        cancelled_tools = await registry.cancel_all()
        if cancelled_tools > 0:
            print(f"[Interruption Handler] Cancelled {cancelled_tools} active tool(s).")
        
        # 3. If agent is still PROCESSING (not started streaming yet) -> Cancel it
        # Note: If STREAMING, let it continue generating (we already cleared its output queues)
        if agent_status == Status.PROCESSING:
            print("[Interruption Handler] Agent is PROCESSING (not streaming yet). Cancelling.")
            ai_agent.cancel()
            agent_was_cancelled = True
            print("[Interruption Handler] Agent cancelled.")
        
        elif agent_status == Status.STREAMING:
            print("[Interruption Handler] Agent is STREAMING. Letting it continue (queues cleared).")
        
        # Unlock: Mark that an interruption has been handled
        self.interruption_status = InterruptionStatus.ACTIVE
        
        return self.interruption_status, agent_was_cancelled

