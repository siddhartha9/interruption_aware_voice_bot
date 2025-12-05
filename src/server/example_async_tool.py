"""
Example Async Tool - Complete Template
=====================================

This file demonstrates how to create a cancellable async tool from scratch.
Use this as a template for any new async tools (API calls, DB operations, etc.)

Pattern Overview:
1. Define the tool function (what the AI agent calls)
2. Define background work function (the actual async logic)
3. Define cancellation function (cleanup logic)
4. Register with ActiveToolRegistry
5. Schedule on background event loop
"""

import asyncio
import threading
from typing import Dict, Optional

from langchain_core.tools import tool

from .active_tool_registry import get_active_tool_registry
from .tool_event_loop import get_tool_event_loop


# ============================================================================
# EXAMPLE 1: Simple Async Tool with Cooperative Cancellation
# ============================================================================

@tool
def book_calendar(date: str, time: str, title: str) -> str:
    """
    Book a calendar appointment (example async tool).
    
    Args:
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format
        title: Appointment title
        
    Returns:
        Confirmation message with tracking ID
    """
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    
    # Threading primitives for sync/async coordination
    cancel_event = threading.Event()
    registration_complete = threading.Event()
    tool_id_holder: Dict[str, Optional[str]] = {"tool_id": None}
    error_holder: Dict[str, Optional[Exception]] = {"error": None}
    
    # ========================================================================
    # STEP 1: Define the background work function
    # ========================================================================
    async def _book_appointment_background(tool_id: str):
        """
        This is where your actual async work happens.
        Check cancel_event periodically for cooperative cancellation.
        """
        try:
            print(f"[Book Calendar] Starting booking for {date} {time} (tool_id={tool_id})")
            
            # Simulate multi-step API workflow
            steps = [
                ("Validating date/time", 0.5),
                ("Checking availability", 1.0),
                ("Reserving slot", 0.8),
                ("Sending confirmation email", 1.2),
                ("Updating calendar", 0.5),
            ]
            
            for i, (step_name, duration) in enumerate(steps):
                # Check for cancellation before each step
                if cancel_event.is_set():
                    print(f"[Book Calendar] ❌ Cancelled at step {i+1}/{len(steps)}: {step_name}")
                    
                    # CLEANUP: Undo any partial work
                    if i >= 2:  # If we reserved a slot, release it
                        print(f"[Book Calendar] 🔄 Releasing reserved slot...")
                        await asyncio.sleep(0.2)  # Simulate API cleanup call
                    
                    # Could also update DB status here
                    # await db.mark_booking_cancelled(tool_id)
                    
                    return
                
                print(f"[Book Calendar] Step {i+1}/{len(steps)}: {step_name}...")
                
                # Simulate async work (API call, DB query, etc.)
                # Break into smaller chunks to check cancel_event more frequently
                for _ in range(int(duration * 10)):
                    if cancel_event.is_set():
                        print(f"[Book Calendar] ❌ Cancelled during {step_name}")
                        return
                    await asyncio.sleep(0.1)
            
            # Final check before marking complete
            if cancel_event.is_set():
                print(f"[Book Calendar] ❌ Cancelled before completion")
                return
            
            print(f"[Book Calendar] ✅ Booking complete! (tool_id={tool_id})")
            
        except Exception as exc:
            print(f"[Book Calendar] ❌ Error: {exc}")
            error_holder["error"] = exc
        finally:
            # Always unregister when done
            await registry.unregister_tool(tool_id)
            print(f"[Book Calendar] Unregistered tool {tool_id}")
    
    # ========================================================================
    # STEP 2: Define the cancellation function
    # ========================================================================
    async def _cancel_booking():
        """
        This is called when the user interrupts.
        Set the cancel flag to stop background work.
        """
        print(f"[Book Calendar] 🛑 Cancel requested!")
        cancel_event.set()
        
        # You can add immediate cleanup here if needed
        # For example, send a "cancel booking" API call
        # await calendar_api.cancel_booking(tool_id)
    
    # ========================================================================
    # STEP 3: Register the tool and start background work
    # ========================================================================
    async def _register_and_start():
        """Register with ActiveToolRegistry and launch background task."""
        try:
            tool_id = await registry.register_tool(
                tool_name="book_calendar",
                cancel_async_fn=_cancel_booking,
                metadata={
                    "date": date,
                    "time": time,
                    "title": title,
                    "status": "in_progress"
                },
            )
            tool_id_holder["tool_id"] = tool_id
            registration_complete.set()
            
            # Start the actual work (don't await, let it run in background)
            asyncio.create_task(_book_appointment_background(tool_id))
            
        except Exception as exc:
            error_holder["error"] = exc
            registration_complete.set()
    
    # ========================================================================
    # STEP 4: Schedule on background event loop and wait for registration
    # ========================================================================
    if not tool_loop.schedule_task(_register_and_start):
        raise RuntimeError("Failed to schedule book_calendar tool on background loop")
    
    # Wait for registration to complete (ensures tool_id is set)
    registration_complete.wait(timeout=5.0)
    
    if error_holder.get("error"):
        raise error_holder["error"]
    
    tool_id = tool_id_holder.get("tool_id")
    if not tool_id:
        raise RuntimeError("Failed to register book_calendar tool")
    
    # Return immediately to the AI agent (work continues in background)
    return (
        f"✅ Booking '{title}' for {date} at {time}. "
        f"You'll receive a confirmation email shortly. "
        f"(tracking_id={tool_id[:8]})"
    )


# ============================================================================
# EXAMPLE 2: Async Tool with Database Cleanup
# ============================================================================

@tool
def process_payment(amount: float, account: str) -> str:
    """
    Process a payment (example with DB cleanup on cancel).
    
    Args:
        amount: Payment amount in dollars
        account: Target account ID
        
    Returns:
        Confirmation message
    """
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    
    cancel_event = threading.Event()
    registration_complete = threading.Event()
    tool_id_holder: Dict[str, Optional[str]] = {"tool_id": None}
    transaction_id_holder: Dict[str, Optional[str]] = {"txn_id": None}
    
    async def _process_payment_background(tool_id: str):
        """Background payment processing with transaction rollback on cancel."""
        txn_id = None
        try:
            print(f"[Payment] Processing ${amount} to {account} (tool_id={tool_id})")
            
            # Step 1: Create transaction record
            # In real code: txn_id = await db.create_transaction(...)
            txn_id = f"TXN_{tool_id[:8]}"
            transaction_id_holder["txn_id"] = txn_id
            print(f"[Payment] Created transaction {txn_id}")
            
            if cancel_event.is_set():
                await _rollback_transaction(txn_id)
                return
            
            await asyncio.sleep(1.0)  # Simulate processing
            
            # Step 2: Check account balance
            if cancel_event.is_set():
                await _rollback_transaction(txn_id)
                return
            
            print(f"[Payment] Balance check passed")
            await asyncio.sleep(0.5)
            
            # Step 3: Transfer funds
            if cancel_event.is_set():
                await _rollback_transaction(txn_id)
                return
            
            print(f"[Payment] Transferring funds...")
            await asyncio.sleep(1.5)
            
            # Step 4: Mark as complete
            if cancel_event.is_set():
                await _rollback_transaction(txn_id)
                return
            
            # In real code: await db.mark_transaction_complete(txn_id)
            print(f"[Payment] ✅ Payment complete! Transaction {txn_id}")
            
        except Exception as exc:
            print(f"[Payment] ❌ Error: {exc}")
            if txn_id:
                await _rollback_transaction(txn_id)
        finally:
            await registry.unregister_tool(tool_id)
    
    async def _rollback_transaction(txn_id: str):
        """Rollback transaction on cancellation."""
        print(f"[Payment] 🔄 Rolling back transaction {txn_id}...")
        # In real code: await db.mark_transaction_cancelled(txn_id)
        await asyncio.sleep(0.3)
        print(f"[Payment] ✅ Rollback complete for {txn_id}")
    
    async def _cancel_payment():
        """Cancel payment and trigger rollback."""
        print(f"[Payment] 🛑 Payment cancellation requested!")
        cancel_event.set()
        
        # Could also send immediate cancel to payment gateway
        # txn_id = transaction_id_holder.get("txn_id")
        # if txn_id:
        #     await payment_gateway.cancel(txn_id)
    
    async def _register_and_start():
        try:
            tool_id = await registry.register_tool(
                tool_name="process_payment",
                cancel_async_fn=_cancel_payment,
                metadata={
                    "amount": amount,
                    "account": account,
                    "status": "pending"
                },
            )
            tool_id_holder["tool_id"] = tool_id
            registration_complete.set()
            asyncio.create_task(_process_payment_background(tool_id))
        except Exception as exc:
            registration_complete.set()
            raise exc
    
    if not tool_loop.schedule_task(_register_and_start):
        raise RuntimeError("Failed to schedule process_payment tool")
    
    registration_complete.wait(timeout=5.0)
    
    tool_id = tool_id_holder.get("tool_id")
    if not tool_id:
        raise RuntimeError("Failed to register process_payment tool")
    
    return (
        f"✅ Processing payment of ${amount} to account {account}. "
        f"You'll receive a confirmation once complete. "
        f"(tracking_id={tool_id[:8]})"
    )


# ============================================================================
# EXAMPLE 3: Async Tool with External API Call
# ============================================================================

@tool
def fetch_weather(city: str) -> str:
    """
    Fetch weather forecast (example with external API).
    
    Args:
        city: City name
        
    Returns:
        Weather forecast
    """
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    
    cancel_event = threading.Event()
    registration_complete = threading.Event()
    tool_id_holder: Dict[str, Optional[str]] = {"tool_id": None}
    result_holder: Dict[str, Optional[str]] = {"result": None}
    
    async def _fetch_weather_background(tool_id: str):
        """Fetch weather with timeout and cancellation."""
        try:
            print(f"[Weather] Fetching forecast for {city} (tool_id={tool_id})")
            
            # In real code, use aiohttp with timeout
            # async with aiohttp.ClientSession() as session:
            #     async with session.get(
            #         f"https://api.weather.com/forecast?city={city}",
            #         timeout=aiohttp.ClientTimeout(total=5.0)
            #     ) as response:
            #         data = await response.json()
            
            # Simulate API call with cancellation check
            for i in range(20):
                if cancel_event.is_set():
                    print(f"[Weather] ❌ Cancelled during API call")
                    return
                await asyncio.sleep(0.1)
            
            if cancel_event.is_set():
                return
            
            # Mock result
            result = f"Weather in {city}: Sunny, 72°F, 20% chance of rain"
            result_holder["result"] = result
            print(f"[Weather] ✅ Forecast retrieved: {result}")
            
        except Exception as exc:
            print(f"[Weather] ❌ Error: {exc}")
        finally:
            await registry.unregister_tool(tool_id)
    
    async def _cancel_weather():
        print(f"[Weather] 🛑 Weather fetch cancelled")
        cancel_event.set()
    
    async def _register_and_start():
        try:
            tool_id = await registry.register_tool(
                tool_name="fetch_weather",
                cancel_async_fn=_cancel_weather,
                metadata={"city": city},
            )
            tool_id_holder["tool_id"] = tool_id
            registration_complete.set()
            await _fetch_weather_background(tool_id)  # Await inline for result
            
            # Send result back to agent via result_holder
            
        except Exception as exc:
            registration_complete.set()
            raise exc
    
    if not tool_loop.schedule_task(_register_and_start):
        raise RuntimeError("Failed to schedule fetch_weather tool")
    
    registration_complete.wait(timeout=10.0)  # Longer timeout for API call
    
    result = result_holder.get("result")
    if result:
        return result
    
    if cancel_event.is_set():
        return f"Weather fetch for {city} was cancelled."
    
    return f"Failed to fetch weather for {city}."


# ============================================================================
# How to Use These Tools
# ============================================================================

"""
To use these example tools in your agent:

1. Import them in your tools.py or ai_agent.py:
   
   from .example_async_tool import book_calendar, process_payment, fetch_weather

2. Add to your tool list:
   
   tools = [
       check_account_balance,
       email_bank_statement,
       book_calendar,        # New!
       process_payment,      # New!
       fetch_weather,        # New!
   ]

3. The tools are automatically cancellable when the user interrupts:
   - orchestrator.py calls ai_agent.cancel()
   - ai_agent.cancel() calls ActiveToolRegistry.cancel_all_tools()
   - Registry calls each tool's _cancel_* function
   - Cancel event is set, background work stops
   - Cleanup logic runs (rollback, API cancel, etc.)

4. For your own tools, copy the pattern from book_calendar:
   - Define background work with cancel_event checks
   - Define cancel function
   - Register with metadata
   - Schedule on background loop
   - Return immediately to agent
"""

