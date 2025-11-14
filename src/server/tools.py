"""
Tools Module.

Only the banking-related tools required by the agent are defined here.
"""

import asyncio
import threading
from typing import List

from langchain_core.tools import tool

from .active_tool_registry import get_active_tool_registry
from .tool_event_loop import get_tool_event_loop


# ============================================================================
# SYNCHRONOUS TOOLS
# ============================================================================

@tool
def check_account_balance() -> str:
    """Return the user's account balance (mock implementation)."""
    return "Your current account balance is 10 crores."


# ============================================================================
# ASYNCHRONOUS TOOLS
# ============================================================================

@tool
def email_bank_statement(email: str) -> str:
    """Email the user's bank statement asynchronously (mock implementation)."""
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    cancelled = threading.Event()

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
        tool_id = await registry.register_tool(
            tool_name="email_bank_statement",
            cancel_async_fn=_cancel_statement,
            metadata={"email": email}
        )
        asyncio.create_task(_send_statement_background(tool_id))

    tool_loop.schedule_task(_register_and_start)
    return f"Your bank statement will be emailed to {email} shortly."


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

