"""
Async Tool Helper Module.

Provides utilities for scheduling async tasks from synchronous tool contexts.
Essential for tools that need to run background operations.
"""

import asyncio
import threading
from typing import Callable, Optional, Any, Dict
from .active_tool_registry import get_active_tool_registry


class AsyncTaskScheduler:
    """
    Schedules async tasks from synchronous contexts.
    
    This class provides a safe way for tools (which are executed synchronously
    by LangChain) to schedule async background tasks.
    """
    
    def __init__(self):
        """Initialize the async task scheduler."""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._task_queue: asyncio.Queue = None
        self._lock = threading.Lock()
        print("[Async Task Scheduler] Initialized")
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """
        Set the event loop to use for scheduling tasks.
        
        Args:
            loop: The asyncio event loop to use
        """
        with self._lock:
            self._loop = loop
            print("[Async Task Scheduler] Event loop set")
    
    def get_event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Get the current event loop.
        
        Returns:
            The event loop if set, None otherwise
        """
        with self._lock:
            if self._loop is not None:
                return self._loop
            
            # Try to get the running event loop
            try:
                return asyncio.get_running_loop()
            except RuntimeError:
                return None
    
    def schedule_task(self, coro: Callable) -> bool:
        """
        Schedule an async task from a synchronous context.
        
        Args:
            coro: Async coroutine or callable that returns a coroutine
            
        Returns:
            True if task was scheduled, False otherwise
        """
        loop = self.get_event_loop()
        
        if loop is None:
            print("[Async Task Scheduler] No event loop available. Creating background thread.")
            self._start_background_loop()
            loop = self._loop
        
        if loop is None:
            print("[Async Task Scheduler] Failed to get event loop")
            return False
        
        # Schedule the task
        try:
            if asyncio.iscoroutine(coro):
                asyncio.run_coroutine_threadsafe(coro, loop)
            elif callable(coro):
                result = coro()
                if asyncio.iscoroutine(result):
                    asyncio.run_coroutine_threadsafe(result, loop)
                else:
                    # It's a regular function, execute in thread pool
                    loop.run_in_executor(None, result)
            else:
                print("[Async Task Scheduler] Invalid coroutine type")
                return False
            
            return True
        except Exception as e:
            print(f"[Async Task Scheduler] Error scheduling task: {e}")
            return False
    
    def _start_background_loop(self):
        """Start a background event loop in a separate thread."""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return
        
        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
            loop.run_forever()
        
        self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
        self._loop_thread.start()
        print("[Async Task Scheduler] Background event loop started")


# Global scheduler instance
_scheduler: Optional[AsyncTaskScheduler] = None


def get_scheduler() -> AsyncTaskScheduler:
    """
    Get the global async task scheduler instance.
    
    Returns:
        AsyncTaskScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncTaskScheduler()
    return _scheduler


def schedule_async_tool(
    tool_name: str,
    background_task: Callable,
    cancel_fn: Optional[Callable] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Schedule an async tool execution.
    
    This is a convenience function that:
    1. Registers the tool in the active tool registry
    2. Schedules the background task
    3. Returns a tool ID
    
    Args:
        tool_name: Name of the tool
        background_task: Async coroutine to run in the background
        cancel_fn: Optional cancellation function
        metadata: Optional metadata about the tool execution
        
    Returns:
        Tool ID for tracking
    """
    registry = get_active_tool_registry()
    scheduler = get_scheduler()
    
    # Register the tool
    async def _register():
        tool_id = await registry.register_tool(
            tool_name=tool_name,
            cancel_async_fn=cancel_fn,
            metadata=metadata or {}
        )
        return tool_id
    
    # Get event loop
    loop = scheduler.get_event_loop()
    
    if loop is None:
        # No loop available, use a simple approach
        # Create a new task in a background thread
        tool_id = None
        
        async def _run_with_cleanup():
            nonlocal tool_id
            tool_id = await registry.register_tool(
                tool_name=tool_name,
                cancel_async_fn=cancel_fn,
                metadata=metadata or {}
            )
            try:
                await background_task()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Async Tool Helper] Error in {tool_name}: {e}")
            finally:
                if tool_id:
                    await registry.unregister_tool(tool_id)
        
        # Schedule in background
        scheduler.schedule_task(_run_with_cleanup())
        return "pending"  # Return a placeholder ID
    
    # We have a loop, use it
    try:
        # Register tool
        tool_id_future = asyncio.run_coroutine_threadsafe(
            registry.register_tool(
                tool_name=tool_name,
                cancel_async_fn=cancel_fn,
                metadata=metadata or {}
            ),
            loop
        )
        tool_id = tool_id_future.result(timeout=1.0)
        
        # Schedule background task
        async def _run_with_cleanup():
            try:
                await background_task()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Async Tool Helper] Error in {tool_name}: {e}")
            finally:
                await registry.unregister_tool(tool_id)
        
        asyncio.run_coroutine_threadsafe(_run_with_cleanup(), loop)
        return tool_id
    except Exception as e:
        print(f"[Async Tool Helper] Error scheduling {tool_name}: {e}")
        return "error"

