"""
Programmatic Tool Caller - Call tools from any module with proper registration.

This module provides utilities to invoke tools programmatically from any part of
your codebase (orchestrator, webhooks, background tasks, etc.) while ensuring
they are properly registered in the ActiveToolRegistry for cancellation.

Usage:
    from .programmatic_tool_caller import call_tool, call_tool_async
    
    # From orchestrator or any other module:
    result = await call_tool_async("book_calendar", 
                                   date="2024-12-10", 
                                   time="14:00", 
                                   title="Meeting")
"""

import asyncio
import inspect
from typing import Any, Dict, Optional

from .active_tool_registry import get_active_tool_registry
from .tools import TOOLS


# ============================================================================
# METHOD 1: Call by Tool Name (Recommended)
# ============================================================================

async def call_tool_async(
    tool_name: str,
    **kwargs
) -> Any:
    """
    Call a tool by name from any module, with proper registry tracking.
    
    This function:
    - Looks up the tool by name
    - Calls it with provided arguments
    - Ensures it gets registered in ActiveToolRegistry
    - Returns the result
    
    Args:
        tool_name: Name of the tool (e.g., "book_calendar")
        **kwargs: Tool arguments (e.g., date="2024-12-10", time="14:00")
        
    Returns:
        Tool result
        
    Example:
        # From orchestrator.py:
        result = await call_tool_async(
            "book_calendar",
            date="2024-12-10",
            time="14:00",
            title="Team Meeting"
        )
        print(result)  # "✅ Booking 'Team Meeting'... (tracking_id=abc123)"
    """
    # Find the tool function by name
    tool_func = None
    for tool in TOOLS:
        if tool.name == tool_name:
            tool_func = tool.func
            break
    
    if not tool_func:
        raise ValueError(f"Tool '{tool_name}' not found. Available: {[t.name for t in TOOLS]}")
    
    print(f"[Programmatic Tool Call] Calling {tool_name} with args: {kwargs}")
    
    # Call the tool function
    # The tool function itself handles registration via tool_loop.schedule_task()
    if inspect.iscoroutinefunction(tool_func):
        # Async tool
        result = await tool_func(**kwargs)
    else:
        # Sync tool (runs in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tool_func(**kwargs))
    
    print(f"[Programmatic Tool Call] {tool_name} returned: {result[:100] if isinstance(result, str) else result}")
    return result


def call_tool_sync(tool_name: str, **kwargs) -> Any:
    """
    Synchronous wrapper for calling tools from non-async code.
    
    Args:
        tool_name: Name of the tool
        **kwargs: Tool arguments
        
    Returns:
        Tool result
        
    Example:
        # From a Flask route or sync function:
        result = call_tool_sync("check_account_balance")
        print(result)  # "Your current account balance is 10 crores."
    """
    print(f"[Programmatic Tool Call - Sync] Calling {tool_name} with args: {kwargs}")
    
    # Find the tool
    tool_func = None
    for tool in TOOLS:
        if tool.name == tool_name:
            tool_func = tool.func
            break
    
    if not tool_func:
        raise ValueError(f"Tool '{tool_name}' not found. Available: {[t.name for t in TOOLS]}")
    
    # Call directly (the tool handles async internally)
    result = tool_func(**kwargs)
    
    print(f"[Programmatic Tool Call - Sync] {tool_name} returned: {result[:100] if isinstance(result, str) else result}")
    return result


# ============================================================================
# METHOD 2: Direct Import (Alternative)
# ============================================================================

"""
You can also import and call tools directly:

from .tools import book_calendar, check_account_balance, email_bank_statement

# Call directly (automatically registers)
result = book_calendar(date="2024-12-10", time="14:00", title="Meeting")

# Or with async wrapper:
async def my_function():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, 
        lambda: book_calendar(date="2024-12-10", time="14:00", title="Meeting")
    )
    return result

This works because:
1. The tool function itself calls tool_loop.schedule_task(_register_and_start)
2. Registration happens inside the tool, not in LangChain's ToolNode
3. All the same registry tracking and cancellation logic applies
"""


# ============================================================================
# METHOD 3: Batch Tool Calls
# ============================================================================

async def call_tools_batch(
    tool_calls: list[tuple[str, Dict[str, Any]]]
) -> list[Any]:
    """
    Call multiple tools in parallel.
    
    Args:
        tool_calls: List of (tool_name, kwargs) tuples
        
    Returns:
        List of results in the same order
        
    Example:
        results = await call_tools_batch([
            ("check_account_balance", {}),
            ("book_calendar", {"date": "2024-12-10", "time": "14:00", "title": "Meeting"}),
            ("email_bank_statement", {"email": "user@example.com"}),
        ])
        
        balance, booking, email_status = results
    """
    print(f"[Batch Tool Call] Calling {len(tool_calls)} tools in parallel")
    
    tasks = [
        call_tool_async(tool_name, **kwargs)
        for tool_name, kwargs in tool_calls
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print(f"[Batch Tool Call] {len(results)} tools completed")
    return results


# ============================================================================
# METHOD 4: Tool Call with Timeout
# ============================================================================

async def call_tool_with_timeout(
    tool_name: str,
    timeout: float = 10.0,
    **kwargs
) -> Any:
    """
    Call a tool with a timeout.
    
    Args:
        tool_name: Name of the tool
        timeout: Max time to wait (seconds)
        **kwargs: Tool arguments
        
    Returns:
        Tool result or TimeoutError
        
    Example:
        try:
            result = await call_tool_with_timeout(
                "book_calendar",
                timeout=5.0,
                date="2024-12-10",
                time="14:00",
                title="Meeting"
            )
        except asyncio.TimeoutError:
            print("Tool timed out!")
    """
    print(f"[Tool Call with Timeout] Calling {tool_name} (timeout={timeout}s)")
    
    try:
        result = await asyncio.wait_for(
            call_tool_async(tool_name, **kwargs),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        print(f"[Tool Call with Timeout] {tool_name} timed out after {timeout}s")
        
        # Cancel any active instances of this tool
        registry = get_active_tool_registry()
        active_tools = await registry.get_active_tools()
        for tool_exec in active_tools:
            if tool_exec.tool_name == tool_name:
                print(f"[Tool Call with Timeout] Cancelling timed-out tool: {tool_exec.tool_id}")
                if tool_exec.cancel_async_fn:
                    await tool_exec.cancel_async_fn()
        
        raise


# ============================================================================
# METHOD 5: Tool Call with Retry
# ============================================================================

async def call_tool_with_retry(
    tool_name: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs
) -> Any:
    """
    Call a tool with automatic retry on failure.
    
    Args:
        tool_name: Name of the tool
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries (seconds)
        **kwargs: Tool arguments
        
    Returns:
        Tool result
        
    Example:
        result = await call_tool_with_retry(
            "fetch_weather",
            max_retries=3,
            retry_delay=2.0,
            city="San Francisco"
        )
    """
    print(f"[Tool Call with Retry] Calling {tool_name} (max_retries={max_retries})")
    
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await call_tool_async(tool_name, **kwargs)
            if attempt > 0:
                print(f"[Tool Call with Retry] {tool_name} succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            last_error = e
            print(f"[Tool Call with Retry] {tool_name} failed (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
    
    print(f"[Tool Call with Retry] {tool_name} failed after {max_retries} attempts")
    raise last_error


# ============================================================================
# EXAMPLE USAGE IN DIFFERENT MODULES
# ============================================================================

"""
# ========================================
# EXAMPLE 1: From Orchestrator
# ========================================

# In orchestrator.py:
from .programmatic_tool_caller import call_tool_async

async def handle_user_command(self, command: str):
    if "balance" in command.lower():
        result = await call_tool_async("check_account_balance")
        await self.websocket.send_json({
            "event": "tool_result",
            "result": result
        })


# ========================================
# EXAMPLE 2: From a Webhook
# ========================================

# In server.py (FastAPI endpoint):
from src.server.programmatic_tool_caller import call_tool_async

@app.post("/api/book-appointment")
async def book_appointment_webhook(request: AppointmentRequest):
    result = await call_tool_async(
        "book_calendar",
        date=request.date,
        time=request.time,
        title=request.title
    )
    return {"status": "success", "result": result}


# ========================================
# EXAMPLE 3: From Background Task
# ========================================

# In a scheduled job or cron task:
from src.server.programmatic_tool_caller import call_tool_async

async def daily_statement_job():
    users = ["user1@example.com", "user2@example.com"]
    
    for user_email in users:
        result = await call_tool_async(
            "email_bank_statement",
            email=user_email
        )
        print(f"Sent statement to {user_email}: {result}")


# ========================================
# EXAMPLE 4: From Test Script
# ========================================

# In test_tools.py:
import asyncio
from src.server.programmatic_tool_caller import call_tool_async, call_tool_sync

async def test_all_tools():
    # Test balance check
    balance = await call_tool_async("check_account_balance")
    assert "10 crores" in balance
    
    # Test booking
    booking = await call_tool_async(
        "book_calendar",
        date="2024-12-10",
        time="14:00",
        title="Test Meeting"
    )
    assert "tracking_id" in booking
    
    print("✅ All tools tested successfully!")

# Can also call sync from non-async code:
def test_sync():
    result = call_tool_sync("check_account_balance")
    print(f"Balance: {result}")


# ========================================
# EXAMPLE 5: With Cancellation
# ========================================

# In orchestrator.py:
from .programmatic_tool_caller import call_tool_async
from .active_tool_registry import get_active_tool_registry

async def run_tool_with_user_interrupt_support(self, tool_name: str, **kwargs):
    # Start the tool
    task = asyncio.create_task(call_tool_async(tool_name, **kwargs))
    
    # If user interrupts, cancel all tools
    try:
        result = await task
        return result
    except asyncio.CancelledError:
        # User interrupted - cancel all active tools
        registry = get_active_tool_registry()
        await registry.cancel_all_tools()
        print("All tools cancelled due to user interrupt")
        raise
"""


# ============================================================================
# UTILITY: Check Active Tools
# ============================================================================

async def get_active_tool_status() -> Dict[str, Any]:
    """
    Get status of all currently running tools.
    
    Returns:
        Dict with tool execution details
        
    Example:
        status = await get_active_tool_status()
        print(f"Active tools: {status['count']}")
        for tool in status['tools']:
            print(f"  - {tool['name']} (running for {tool['duration']}s)")
    """
    registry = get_active_tool_registry()
    active_tools = await registry.get_active_tools()
    
    import time
    result = {
        "count": len(active_tools),
        "tools": []
    }
    
    for tool_exec in active_tools:
        duration = time.time() - tool_exec.started_at
        result["tools"].append({
            "id": tool_exec.tool_id,
            "name": tool_exec.tool_name,
            "duration": round(duration, 2),
            "metadata": tool_exec.metadata,
            "is_complete": tool_exec.is_complete,
            "was_cancelled": tool_exec.was_cancelled,
        })
    
    return result


async def cancel_specific_tool(tool_id: str) -> bool:
    """
    Cancel a specific tool by its ID.
    
    Args:
        tool_id: Tool execution ID
        
    Returns:
        True if cancelled, False if not found
        
    Example:
        # Get status
        status = await get_active_tool_status()
        tool_id = status['tools'][0]['id']
        
        # Cancel it
        cancelled = await cancel_specific_tool(tool_id)
    """
    registry = get_active_tool_registry()
    return await registry.cancel_tool(tool_id)

