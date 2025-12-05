# Calling Tools from Any Module - Quick Reference

## 🎯 The Key Insight

**You can call tools from ANY module** (not just the AI agent), and they will **automatically register** in the `ActiveToolRegistry` for proper cancellation.

## 🔑 Why It Works

The registration happens **inside the tool function**, not in LangChain's ToolNode:

```python
@tool
def book_calendar(date: str, time: str, title: str) -> str:
    # ... tool setup ...
    
    async def _register_and_start():
        tool_id = await registry.register_tool(...)  # ← REGISTRATION HERE
        # ... rest of work ...
    
    tool_loop.schedule_task(_register_and_start)  # ← ALWAYS CALLED
    return result
```

**So whether you call it from**:
- ✅ AI Agent (via LangChain)
- ✅ Orchestrator
- ✅ FastAPI webhook
- ✅ Background task
- ✅ Test script
- ✅ ANY Python module

**The tool will register itself!**

---

## 📖 Three Ways to Call Tools

### Method 1: Using `call_tool_async()` (Recommended)

```python
from src.server.programmatic_tool_caller import call_tool_async

# From any async function:
async def my_function():
    result = await call_tool_async(
        "book_calendar",
        date="2024-12-10",
        time="14:00",
        title="Meeting"
    )
    print(result)  # "✅ Booking 'Meeting'... (tracking_id=abc123)"
```

**Pros**: 
- Clean API
- Works from any module
- Automatic error handling
- Easy to add timeout/retry

**Use when**: You want a standardized way to call tools programmatically.

---

### Method 2: Direct Import

```python
from src.server.tools import book_calendar, check_account_balance

# Sync context:
result = book_calendar(date="2024-12-10", time="14:00", title="Meeting")

# Async context:
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(
    None, 
    lambda: book_calendar(date="2024-12-10", time="14:00", title="Meeting")
)
```

**Pros**:
- Direct function call
- Type checking works
- IDE autocomplete

**Use when**: You know exactly which tool you want and prefer direct imports.

---

### Method 3: From Synchronous Code

```python
from src.server.programmatic_tool_caller import call_tool_sync

# From a Flask route or non-async function:
def my_sync_function():
    result = call_tool_sync("check_account_balance")
    print(result)
```

**Use when**: You're in legacy sync code that can't use async/await.

---

## 🔥 Practical Examples

### Example 1: From Orchestrator (Button Click)

```python
# In orchestrator.py:
from .programmatic_tool_caller import call_tool_async

async def on_websocket_event(self, event_type: str, data: dict):
    if event_type == "ui_button_click":
        button = data.get("button")
        
        if button == "check_balance":
            result = await call_tool_async("check_account_balance")
            await self.websocket.send_json({
                "event": "tool_result",
                "result": result
            })
```

---

### Example 2: From FastAPI Webhook

```python
# In server.py:
from fastapi import FastAPI
from src.server.programmatic_tool_caller import call_tool_async

app = FastAPI()

@app.post("/api/book-appointment")
async def book_appointment(request: AppointmentRequest):
    result = await call_tool_async(
        "book_calendar",
        date=request.date,
        time=request.time,
        title=request.title
    )
    return {"status": "success", "result": result}
```

---

### Example 3: From Background Task

```python
# In a scheduled job:
from src.server.programmatic_tool_caller import call_tool_async

async def daily_statement_job():
    """Send daily statements to all users."""
    users = await get_all_users()
    
    for user in users:
        result = await call_tool_async(
            "email_bank_statement",
            email=user.email
        )
        print(f"Sent statement to {user.email}: {result}")
```

---

### Example 4: Batch Operations

```python
from src.server.programmatic_tool_caller import call_tools_batch

async def load_dashboard_data():
    results = await call_tools_batch([
        ("check_account_balance", {}),
        ("email_bank_statement", {"email": "user@example.com"}),
    ])
    
    balance, email_status = results
    return {"balance": balance, "email_status": email_status}
```

---

### Example 5: With Timeout

```python
from src.server.programmatic_tool_caller import call_tool_with_timeout

async def quick_booking():
    try:
        result = await call_tool_with_timeout(
            "book_calendar",
            timeout=5.0,  # Max 5 seconds
            date="2024-12-10",
            time="14:00",
            title="Quick Meeting"
        )
        return result
    except asyncio.TimeoutError:
        return "Booking timed out, please try again"
```

---

### Example 6: With Retry

```python
from src.server.programmatic_tool_caller import call_tool_with_retry

async def reliable_email():
    result = await call_tool_with_retry(
        "email_bank_statement",
        max_retries=3,
        retry_delay=2.0,
        email="user@example.com"
    )
    return result
```

---

## 🛡️ Cancellation Still Works!

Even when calling tools programmatically, they're still cancellable:

```python
# In orchestrator.py:
async def run_tool_and_handle_interrupt(self):
    # Start a tool
    task = asyncio.create_task(
        call_tool_async("book_calendar", date="2024-12-10", ...)
    )
    
    # If user interrupts:
    try:
        result = await task
    except asyncio.CancelledError:
        # Cancel all tools
        await self.active_tool_registry.cancel_all_tools()
        print("Tools cancelled!")
```

**The flow**:
1. User interrupts → `orchestrator.on_user_starts_speaking()`
2. Orchestrator calls `ai_agent.cancel()`
3. Agent calls `registry.cancel_all_tools()`
4. Registry calls each tool's `cancel_async_fn()`
5. Tool's `cancel_event.set()` is triggered
6. Background work stops

**Works the same** whether the tool was called by:
- ✅ AI Agent
- ✅ Programmatic call from orchestrator
- ✅ Webhook
- ✅ Background task

---

## 📊 Monitoring Active Tools

```python
from src.server.programmatic_tool_caller import (
    get_active_tool_status,
    cancel_specific_tool
)

# Check what's running
status = await get_active_tool_status()
print(f"Active tools: {status['count']}")
for tool in status['tools']:
    print(f"  - {tool['name']} (running {tool['duration']}s)")

# Cancel a specific tool
tool_id = status['tools'][0]['id']
await cancel_specific_tool(tool_id)
```

---

## 🎓 Summary Table

| Scenario | Method | Code |
|----------|--------|------|
| From async function | `call_tool_async()` | `await call_tool_async("tool_name", **args)` |
| From sync function | `call_tool_sync()` | `call_tool_sync("tool_name", **args)` |
| Direct import | Import tool | `from .tools import book_calendar; book_calendar(...)` |
| Multiple tools | `call_tools_batch()` | `await call_tools_batch([("tool1", {}), ...])` |
| With timeout | `call_tool_with_timeout()` | `await call_tool_with_timeout("tool", timeout=5.0, ...)` |
| With retry | `call_tool_with_retry()` | `await call_tool_with_retry("tool", max_retries=3, ...)` |

---

## 🔧 Where to Import From

```python
# All programmatic calling utilities:
from src.server.programmatic_tool_caller import (
    call_tool_async,
    call_tool_sync,
    call_tools_batch,
    call_tool_with_timeout,
    call_tool_with_retry,
    get_active_tool_status,
    cancel_specific_tool,
)

# Or import tools directly:
from src.server.tools import (
    check_account_balance,
    email_bank_statement,
    book_calendar,  # If you added this from example_async_tool.py
)

# Registry access:
from src.server.active_tool_registry import get_active_tool_registry
```

---

## ✅ Best Practices

1. **Use `call_tool_async()` for consistency** - Easier to add timeout/retry later
2. **Monitor active tools** - Use `get_active_tool_status()` for debugging
3. **Handle cancellation** - Wrap tool calls in try/except for `CancelledError`
4. **Add timeouts for external APIs** - Use `call_tool_with_timeout()`
5. **Retry transient failures** - Use `call_tool_with_retry()` for unreliable APIs
6. **Log tool execution** - Tools already log, but add context from your module

---

## 🚀 Next Steps

1. **Read**: `src/server/programmatic_tool_caller.py` - All utility functions
2. **Try**: `examples/call_tools_from_any_module.py` - Practical examples
3. **Integrate**: Add tool calls to your orchestrator, webhooks, etc.
4. **Monitor**: Use `get_active_tool_status()` to debug tool execution

**Remember**: Tools automatically register themselves, so calling them from ANY module will work out of the box! 🎉

