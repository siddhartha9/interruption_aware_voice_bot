"""
Tools Module.

Only the banking-related tools required by the agent are defined here.
"""

import asyncio
import threading
from typing import Awaitable, Callable, Dict, List, Optional

from langchain_core.tools import tool

from .active_tool_registry import get_active_tool_registry
from .tool_event_loop import get_tool_event_loop


def _run_sync_tool_with_registry(
    tool_name: str,
    work_coro_factory: Callable[[threading.Event, Optional[Dict]], Awaitable[str]],
    metadata: Optional[Dict] = None,
    cancel_message: str = "Tool execution cancelled.",
) -> str:
    """
    Helper to execute a synchronous tool while registering it with the active
    tool registry and exposing a cancellation hook.
    """
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    
    cancel_event = threading.Event()
    done_event = threading.Event()
    result_holder: Dict[str, str] = {}
    error_holder: Dict[str, Exception] = {}

    async def _cancel():
        cancel_event.set()

    async def _execute():
        tool_id: Optional[str] = None
        try:
            tool_id = await registry.register_tool(
                tool_name=tool_name,
                cancel_async_fn=_cancel,
                metadata=metadata or {},
            )
            result = await work_coro_factory(cancel_event, {"tool_id": tool_id})
            if result is not None:
                result_holder["result"] = result
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            if tool_id is not None:
                await registry.unregister_tool(tool_id)
            done_event.set()

    # Schedule execution on the background tool loop (ensures we can await)
    scheduled = tool_loop.schedule_task(_execute)
    if scheduled:
        done_event.wait()
    else:
        # Fallback: run inline if scheduling fails
        asyncio.run(_execute())

    if error_holder.get("error"):
        raise error_holder["error"]

    if cancel_event.is_set() and "result" not in result_holder:
        return cancel_message

    return result_holder.get("result", cancel_message if cancel_event.is_set() else "")


# ============================================================================
# SYNCHRONOUS TOOLS
# ============================================================================

@tool
def check_account_balance() -> str:
    """Return the user's account balance (mock implementation)."""
    async def _work(cancel_event: threading.Event, context: Optional[Dict]) -> str:
        tool_id = context.get("tool_id") if context else None
        print(f"[Check Account Balance] Started (tool_id={tool_id})")

        steps = 5
        for step in range(steps):
            if cancel_event.is_set():
                print(f"[Check Account Balance] Cancelled at step {step} (tool_id={tool_id})")
                return "Account balance request cancelled."
            await asyncio.sleep(0.1)

        if cancel_event.is_set():
            print(f"[Check Account Balance] Cancelled after completion request (tool_id={tool_id})")
            return "Account balance request cancelled."

        print(f"[Check Account Balance] Completed (tool_id={tool_id})")
        return "Your current account balance is 10 crores."

    return _run_sync_tool_with_registry(
        tool_name="check_account_balance",
        work_coro_factory=_work,
        metadata={"category": "banking", "type": "balance_lookup"},
    )


# ============================================================================
# ASYNCHRONOUS TOOLS
# ============================================================================

@tool
def email_bank_statement(email: str) -> str:
    """Email the user's bank statement asynchronously (mock implementation)."""
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    cancelled = threading.Event()
    registration_complete = threading.Event()
    tool_id_holder: Dict[str, Optional[str]] = {"tool_id": None}
    
    async def _send_statement_background(tool_id: str):
        try:
            print(f"[Email Bank Statement] Preparing statement for {email}...")
            for _ in range(4):
                if cancelled.is_set():
                    print(f"[Email Bank Statement] Cancelled for {email}")
                    return
                await asyncio.sleep(0.5)
            
            if not cancelled.is_set():
                print(f"[Email Bank Statement] ✓ Statement emailed to {email}")
        except asyncio.CancelledError:
            print(f"[Email Bank Statement] Cancelled for {email}")
        except Exception as e:
            print(f"[Email Bank Statement] Error: {e}")
        finally:
            await registry.unregister_tool(tool_id)
    
    async def _cancel_statement():
        cancelled.set()
    
    async def _register_and_start():
        try:
            tool_id = await registry.register_tool(
                    tool_name="email_bank_statement",
                    cancel_async_fn=_cancel_statement,
                    metadata={"email": email},
                )
            tool_id_holder["tool_id"] = tool_id
            registration_complete.set()
            asyncio.create_task(_send_statement_background(tool_id))
        except Exception as exc:
            registration_complete.set()
            raise exc

    if not tool_loop.schedule_task(_register_and_start):
        registration_complete.set()
        raise RuntimeError("Failed to schedule email_bank_statement tool.")
    registration_complete.wait()

    tool_id = tool_id_holder.get("tool_id")
    if not tool_id:
        raise RuntimeError("Failed to register email_bank_statement tool.")
    
    return (
        f"Your bank statement will be emailed to {email} shortly. "
        f"(tracking_id={tool_id[:8]})"
    )


# ============================================================================
# TOOL LISTS (Export for use in AI Agent)
# ============================================================================

SYNC_TOOLS: List = [
    check_account_balance,
]

ASYNC_TOOLS: List = [
    email_bank_statement,
]

TOOLS: List = SYNC_TOOLS + ASYNC_TOOLS

