"""
Tool Event Loop Module.

Provides a background event loop for async tools to run in.
Essential because LangChain tools are executed synchronously.
"""

import asyncio
import threading
from typing import Optional, Callable, Any


class ToolEventLoop:
    """
    Background event loop for async tool operations.
    
    This class provides a thread-safe way to schedule async tasks
    from synchronous tool contexts (LangChain tools are sync).
    """
    
    def __init__(self):
        """Initialize the tool event loop."""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._start_loop()
    
    def _start_loop(self):
        """Start the background event loop in a separate thread."""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return
        
        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
            try:
                loop.run_forever()
            finally:
                loop.close()
        
        self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
        self._loop_thread.start()
        # Wait a bit for loop to start
        import time
        time.sleep(0.1)
    
    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Get the background event loop.
        
        Returns:
            The event loop if available, None otherwise
        """
        with self._lock:
            return self._loop
    
    def schedule_task(self, coro_fn: Callable) -> bool:
        """
        Schedule an async task on the background event loop.
        
        Args:
            coro_fn: Callable that returns an async coroutine
            
        Returns:
            True if task was scheduled, False otherwise
        """
        loop = self.get_loop()
        if loop is None:
            print("[Tool Event Loop] No event loop available")
            return False
        
        try:
            # Get the coroutine from the callable
            if callable(coro_fn):
                coro = coro_fn()
                if asyncio.iscoroutine(coro):
                    # Schedule the coroutine on the background loop
                    asyncio.run_coroutine_threadsafe(coro, loop)
                    return True
                else:
                    print("[Tool Event Loop] Callable did not return a coroutine")
                    return False
            elif asyncio.iscoroutine(coro_fn):
                # Already a coroutine
                asyncio.run_coroutine_threadsafe(coro_fn, loop)
                return True
            else:
                print("[Tool Event Loop] Invalid coroutine type")
                return False
        except Exception as e:
            print(f"[Tool Event Loop] Error scheduling task: {e}")
            import traceback
            traceback.print_exc()
            return False


# Global event loop instance
_tool_loop: Optional[ToolEventLoop] = None


def get_tool_event_loop() -> ToolEventLoop:
    """
    Get the global tool event loop instance.
    
    Returns:
        ToolEventLoop instance
    """
    global _tool_loop
    if _tool_loop is None:
        _tool_loop = ToolEventLoop()
    return _tool_loop
