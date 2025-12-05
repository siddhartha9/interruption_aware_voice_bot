"""
Practical Examples: Calling Tools from Any Module

This file demonstrates how to call tools programmatically from different parts
of your application (not just from the AI agent).

All tool calls shown here will automatically register in ActiveToolRegistry
and can be cancelled when the user interrupts.
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.server.programmatic_tool_caller import (
    call_tool_async,
    call_tool_sync,
    call_tools_batch,
    call_tool_with_timeout,
    call_tool_with_retry,
    get_active_tool_status,
    cancel_specific_tool,
)


# ============================================================================
# EXAMPLE 1: Call Tool from Orchestrator
# ============================================================================

async def example_from_orchestrator():
    """
    Example: Calling a tool from orchestrator.py when handling a WebSocket event.
    
    Use case: User clicks a button in the UI to check balance (not via voice).
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Calling Tool from Orchestrator")
    print("="*70)
    
    # Simulate: User clicked "Check Balance" button in UI
    print("\n[Orchestrator] User clicked 'Check Balance' button")
    print("[Orchestrator] Calling tool programmatically...")
    
    result = await call_tool_async("check_account_balance")
    
    print(f"[Orchestrator] Tool returned: {result}")
    print("[Orchestrator] Sending result to client via WebSocket...")
    # await self.websocket.send_json({"event": "tool_result", "result": result})


# ============================================================================
# EXAMPLE 2: Call Tool from FastAPI Webhook
# ============================================================================

async def example_webhook_endpoint():
    """
    Example: FastAPI endpoint that calls a tool.
    
    Use case: External system sends a webhook to book an appointment.
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Calling Tool from FastAPI Webhook")
    print("="*70)
    
    # Simulate: POST /api/book-appointment
    print("\n[Webhook] Received POST /api/book-appointment")
    print("[Webhook] Request body: {date: '2024-12-15', time: '10:00', title: 'Client Call'}")
    
    result = await call_tool_async(
        "book_calendar",
        date="2024-12-15",
        time="10:00",
        title="Client Call"
    )
    
    print(f"[Webhook] Tool returned: {result}")
    print("[Webhook] Returning 200 OK with result")
    # return JSONResponse({"status": "success", "result": result})


# ============================================================================
# EXAMPLE 3: Call Multiple Tools in Parallel
# ============================================================================

async def example_batch_tools():
    """
    Example: Calling multiple tools at once.
    
    Use case: Dashboard loads and needs to fetch multiple data points.
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Calling Multiple Tools in Parallel")
    print("="*70)
    
    print("\n[Dashboard] Loading user dashboard...")
    print("[Dashboard] Fetching balance, recent transactions, and sending statement...")
    
    results = await call_tools_batch([
        ("check_account_balance", {}),
        ("email_bank_statement", {"email": "user@example.com"}),
    ])
    
    balance, email_status = results
    
    print(f"[Dashboard] Balance: {balance}")
    print(f"[Dashboard] Email Status: {email_status}")
    print("[Dashboard] Dashboard loaded successfully!")


# ============================================================================
# EXAMPLE 4: Call Tool with Timeout
# ============================================================================

async def example_with_timeout():
    """
    Example: Calling a tool with a timeout.
    
    Use case: Don't want to wait forever if external API is slow.
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Calling Tool with Timeout")
    print("="*70)
    
    print("\n[Timeout Example] Calling book_calendar with 3-second timeout...")
    
    try:
        result = await call_tool_with_timeout(
            "book_calendar",
            timeout=3.0,  # Only wait 3 seconds
            date="2024-12-20",
            time="15:00",
            title="Quick Meeting"
        )
        print(f"[Timeout Example] Success: {result}")
    except asyncio.TimeoutError:
        print("[Timeout Example] Tool timed out! Cancelled automatically.")


# ============================================================================
# EXAMPLE 5: Call Tool with Retry
# ============================================================================

async def example_with_retry():
    """
    Example: Calling a tool with automatic retry.
    
    Use case: External API might fail transiently, want to retry.
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Calling Tool with Retry")
    print("="*70)
    
    print("\n[Retry Example] Calling email_bank_statement with retry...")
    
    result = await call_tool_with_retry(
        "email_bank_statement",
        max_retries=3,
        retry_delay=1.0,
        email="user@example.com"
    )
    
    print(f"[Retry Example] Success: {result}")


# ============================================================================
# EXAMPLE 6: Monitor Active Tools
# ============================================================================

async def example_monitor_tools():
    """
    Example: Monitoring active tool executions.
    
    Use case: Admin dashboard showing what tools are currently running.
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: Monitoring Active Tools")
    print("="*70)
    
    # Start a long-running tool
    print("\n[Monitor] Starting a long-running tool...")
    task = asyncio.create_task(call_tool_async(
        "book_calendar",
        date="2024-12-25",
        time="09:00",
        title="Holiday Planning"
    ))
    
    # Wait a bit
    await asyncio.sleep(0.5)
    
    # Check status
    print("\n[Monitor] Checking active tools...")
    status = await get_active_tool_status()
    
    print(f"[Monitor] Active tool count: {status['count']}")
    for tool in status['tools']:
        print(f"  - {tool['name']} (ID: {tool['id'][:8]}..., running for {tool['duration']}s)")
    
    # Wait for completion
    result = await task
    print(f"\n[Monitor] Tool completed: {result}")


# ============================================================================
# EXAMPLE 7: Cancel Specific Tool
# ============================================================================

async def example_cancel_specific_tool():
    """
    Example: Cancelling a specific tool by ID.
    
    Use case: User wants to cancel one specific operation, not all.
    """
    print("\n" + "="*70)
    print("EXAMPLE 7: Cancelling Specific Tool")
    print("="*70)
    
    # Start two tools
    print("\n[Cancel Example] Starting two tools...")
    task1 = asyncio.create_task(call_tool_async(
        "book_calendar",
        date="2024-12-30",
        time="14:00",
        title="Meeting 1"
    ))
    task2 = asyncio.create_task(call_tool_async(
        "email_bank_statement",
        email="user1@example.com"
    ))
    
    # Wait a bit
    await asyncio.sleep(0.5)
    
    # Get active tools
    status = await get_active_tool_status()
    print(f"\n[Cancel Example] Active tools: {status['count']}")
    
    if status['tools']:
        # Cancel the first one
        tool_id = status['tools'][0]['id']
        tool_name = status['tools'][0]['name']
        print(f"[Cancel Example] Cancelling {tool_name} (ID: {tool_id[:8]}...)")
        
        cancelled = await cancel_specific_tool(tool_id)
        print(f"[Cancel Example] Cancelled: {cancelled}")
    
    # Wait for remaining tasks
    await asyncio.sleep(2.0)
    print("[Cancel Example] Remaining tools completed")


# ============================================================================
# EXAMPLE 8: From Synchronous Code
# ============================================================================

def example_from_sync_code():
    """
    Example: Calling a tool from synchronous code (non-async).
    
    Use case: Legacy code or Flask endpoints that aren't async.
    """
    print("\n" + "="*70)
    print("EXAMPLE 8: Calling Tool from Synchronous Code")
    print("="*70)
    
    print("\n[Sync Example] This is a synchronous function (no async/await)")
    print("[Sync Example] Calling check_account_balance...")
    
    result = call_tool_sync("check_account_balance")
    
    print(f"[Sync Example] Result: {result}")


# ============================================================================
# EXAMPLE 9: Integration in Orchestrator (Practical)
# ============================================================================

class ExampleOrchestrator:
    """
    Example showing how to integrate tool calls in your orchestrator.
    """
    
    def __init__(self):
        self.websocket = None  # Mock
    
    async def handle_ui_button_click(self, button_type: str):
        """Handle user clicking a button in the UI."""
        print(f"\n[Orchestrator] User clicked button: {button_type}")
        
        if button_type == "check_balance":
            result = await call_tool_async("check_account_balance")
            print(f"[Orchestrator] Sending result to client: {result}")
            # await self.websocket.send_json({"event": "balance", "data": result})
        
        elif button_type == "email_statement":
            result = await call_tool_async(
                "email_bank_statement",
                email="user@example.com"
            )
            print(f"[Orchestrator] Sending result to client: {result}")
            # await self.websocket.send_json({"event": "email_sent", "data": result})
    
    async def scheduled_task(self):
        """Example: Background task that runs periodically."""
        print("\n[Orchestrator] Running scheduled task...")
        
        # Send daily statement to all users
        users = ["user1@example.com", "user2@example.com"]
        
        for user_email in users:
            result = await call_tool_async(
                "email_bank_statement",
                email=user_email
            )
            print(f"[Orchestrator] Sent statement to {user_email}: {result}")


async def example_orchestrator_integration():
    """Run the orchestrator examples."""
    print("\n" + "="*70)
    print("EXAMPLE 9: Orchestrator Integration")
    print("="*70)
    
    orchestrator = ExampleOrchestrator()
    
    # Simulate UI button clicks
    await orchestrator.handle_ui_button_click("check_balance")
    await asyncio.sleep(1.0)
    
    await orchestrator.handle_ui_button_click("email_statement")
    await asyncio.sleep(2.0)


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

async def run_all_examples():
    """Run all examples in sequence."""
    print("\n" + "="*70)
    print("🚀 TOOL CALLING FROM ANY MODULE - PRACTICAL EXAMPLES")
    print("="*70)
    
    # Run examples
    await example_from_orchestrator()
    await asyncio.sleep(1)
    
    await example_webhook_endpoint()
    await asyncio.sleep(1)
    
    await example_batch_tools()
    await asyncio.sleep(2)
    
    # await example_with_timeout()  # Uncomment to test timeout
    # await asyncio.sleep(1)
    
    await example_with_retry()
    await asyncio.sleep(2)
    
    await example_monitor_tools()
    await asyncio.sleep(2)
    
    # await example_cancel_specific_tool()  # Uncomment to test cancellation
    # await asyncio.sleep(3)
    
    example_from_sync_code()
    await asyncio.sleep(1)
    
    await example_orchestrator_integration()
    
    print("\n" + "="*70)
    print("✅ ALL EXAMPLES COMPLETED!")
    print("="*70)


if __name__ == "__main__":
    # Note: This is a standalone example. To run it:
    # 1. Start the tool event loop first
    # 2. Then run this script
    
    print("⚠️  Note: This example requires the tool_event_loop to be running.")
    print("    In a real app, the event loop starts when the server starts.")
    print("    For testing, you would start it manually in your test setup.\n")
    
    # asyncio.run(run_all_examples())

