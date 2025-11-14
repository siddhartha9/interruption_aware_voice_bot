"""
Active Tool Registry Module.

This module tracks active tool executions and provides cancellation support.
Essential for interrupting long-running or async tool operations.
"""

import asyncio
import uuid
from typing import Dict, Optional, Callable, Any, List
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ToolExecution:
    """
    Represents an active tool execution.
    
    Tracks the execution state and provides cancellation support.
    """
    tool_id: str
    tool_name: str
    started_at: datetime
    cancel_fn: Optional[Callable[[], None]] = None
    cancel_async_fn: Optional[Callable[[], Any]] = None
    is_complete: bool = False
    was_cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def cancel(self) -> bool:
        """
        Cancel this tool execution.
        
        Returns:
            True if cancellation was successful, False otherwise
        """
        if self.is_complete:
            return False
        
        if self.was_cancelled:
            return False
        
        try:
            # Try async cancellation first
            if self.cancel_async_fn:
                # Schedule async cancellation
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.cancel_async_fn())
                else:
                    loop.run_until_complete(self.cancel_async_fn())
                self.was_cancelled = True
                return True
            
            # Fall back to sync cancellation
            if self.cancel_fn:
                self.cancel_fn()
                self.was_cancelled = True
                return True
            
            # No cancellation function available
            return False
        except Exception as e:
            print(f"[Tool Execution] Error cancelling {self.tool_name} ({self.tool_id}): {e}")
            return False
    
    async def cancel_async(self) -> bool:
        """
        Cancel this tool execution asynchronously.
        
        Returns:
            True if cancellation was successful, False otherwise
        """
        if self.is_complete:
            return False
        
        if self.was_cancelled:
            return False
        
        try:
            # Try async cancellation first
            if self.cancel_async_fn:
                await self.cancel_async_fn()
                self.was_cancelled = True
                return True
            
            # Fall back to sync cancellation
            if self.cancel_fn:
                # Run sync cancellation in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.cancel_fn)
                self.was_cancelled = True
                return True
            
            # No cancellation function available
            return False
        except Exception as e:
            print(f"[Tool Execution] Error cancelling {self.tool_name} ({self.tool_id}): {e}")
            return False
    
    def mark_complete(self):
        """Mark this tool execution as complete."""
        self.is_complete = True
    
    def get_duration(self) -> float:
        """
        Get the duration of this execution in seconds.
        
        Returns:
            Duration in seconds
        """
        return (datetime.now() - self.started_at).total_seconds()


class ActiveToolRegistry:
    """
    Registry for tracking active tool executions.
    
    Provides functionality to:
    - Register tool executions
    - Cancel individual tools
    - Cancel all active tools (useful for interruptions)
    - Query active tools
    """
    
    def __init__(self):
        """Initialize the active tool registry."""
        self._active_tools: Dict[str, ToolExecution] = {}
        self._lock = asyncio.Lock()
        print("[Active Tool Registry] Initialized")
    
    async def register_tool(
        self,
        tool_name: str,
        cancel_fn: Optional[Callable[[], None]] = None,
        cancel_async_fn: Optional[Callable[[], Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register a new active tool execution.
        
        Args:
            tool_name: Name of the tool being executed
            cancel_fn: Synchronous cancellation function (optional)
            cancel_async_fn: Asynchronous cancellation function (optional)
            metadata: Additional metadata about the tool execution (optional)
            
        Returns:
            Unique tool ID for this execution
        """
        tool_id = str(uuid.uuid4())
        
        execution = ToolExecution(
            tool_id=tool_id,
            tool_name=tool_name,
            started_at=datetime.now(),
            cancel_fn=cancel_fn,
            cancel_async_fn=cancel_async_fn,
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._active_tools[tool_id] = execution
        
        print(f"[Active Tool Registry] Registered tool: {tool_name} (ID: {tool_id[:8]}...)")
        return tool_id
    
    async def unregister_tool(self, tool_id: str) -> bool:
        """
        Unregister a tool execution (mark as complete).
        
        Args:
            tool_id: Unique tool ID
            
        Returns:
            True if tool was found and unregistered, False otherwise
        """
        async with self._lock:
            if tool_id in self._active_tools:
                execution = self._active_tools[tool_id]
                execution.mark_complete()
                duration = execution.get_duration()
                print(f"[Active Tool Registry] Unregistered tool: {execution.tool_name} (ID: {tool_id[:8]}..., duration: {duration:.2f}s)")
                del self._active_tools[tool_id]
                return True
            return False
    
    async def cancel_tool(self, tool_id: str) -> bool:
        """
        Cancel a specific tool execution.
        
        Args:
            tool_id: Unique tool ID
            
        Returns:
            True if tool was found and cancelled, False otherwise
        """
        async with self._lock:
            if tool_id in self._active_tools:
                execution = self._active_tools[tool_id]
                success = await execution.cancel_async()
                if success:
                    print(f"[Active Tool Registry] Cancelled tool: {execution.tool_name} (ID: {tool_id[:8]}...)")
                    # Don't unregister immediately - let cleanup happen naturally
                return success
            return False
    
    async def cancel_all(self) -> int:
        """
        Cancel all active tool executions.
        
        This is typically called during interruptions to clean up
        all ongoing tool operations.
        
        Returns:
            Number of tools cancelled
        """
        async with self._lock:
            if not self._active_tools:
                return 0
            
            tool_ids = list(self._active_tools.keys())
            cancelled_count = 0
            
            print(f"[Active Tool Registry] Cancelling {len(tool_ids)} active tool(s)...")
            
            # Cancel all tools
            for tool_id in tool_ids:
                execution = self._active_tools[tool_id]
                try:
                    success = await execution.cancel_async()
                    if success:
                        cancelled_count += 1
                except Exception as e:
                    print(f"[Active Tool Registry] Error cancelling {execution.tool_name} ({tool_id[:8]}...): {e}")
            
            if cancelled_count > 0:
                print(f"[Active Tool Registry] ✓ Cancelled {cancelled_count}/{len(tool_ids)} tool(s)")
            
            return cancelled_count
    
    async def get_active_tools(self) -> List[ToolExecution]:
        """
        Get list of all active tool executions.
        
        Returns:
            List of ToolExecution objects
        """
        async with self._lock:
            return list(self._active_tools.values())
    
    async def get_active_tool_count(self) -> int:
        """
        Get the number of active tool executions.
        
        Returns:
            Number of active tools
        """
        async with self._lock:
            return len(self._active_tools)
    
    async def get_tool(self, tool_id: str) -> Optional[ToolExecution]:
        """
        Get a specific tool execution by ID.
        
        Args:
            tool_id: Unique tool ID
            
        Returns:
            ToolExecution if found, None otherwise
        """
        async with self._lock:
            return self._active_tools.get(tool_id)
    
    async def clear_completed(self):
        """
        Remove all completed tool executions from registry.
        
        Useful for cleanup to prevent memory leaks.
        """
        async with self._lock:
            completed_ids = [
                tool_id for tool_id, execution in self._active_tools.items()
                if execution.is_complete
            ]
            
            for tool_id in completed_ids:
                del self._active_tools[tool_id]
            
            if completed_ids:
                print(f"[Active Tool Registry] Cleared {len(completed_ids)} completed tool(s)")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the registry status.
        
        Returns:
            Dictionary with status information
        """
        active_count = len(self._active_tools)
        active_tools = [
            {
                "tool_id": exec.tool_id[:8],
                "tool_name": exec.tool_name,
                "duration": exec.get_duration(),
                "is_complete": exec.is_complete,
                "was_cancelled": exec.was_cancelled,
            }
            for exec in self._active_tools.values()
        ]
        
        return {
            "active_count": active_count,
            "active_tools": active_tools,
        }


# Global registry instance (singleton pattern)
_active_tool_registry: Optional[ActiveToolRegistry] = None


def get_active_tool_registry() -> ActiveToolRegistry:
    """
    Get the global active tool registry instance.
    
    Returns:
        ActiveToolRegistry instance
    """
    global _active_tool_registry
    if _active_tool_registry is None:
        _active_tool_registry = ActiveToolRegistry()
    return _active_tool_registry

