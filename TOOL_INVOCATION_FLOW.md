# Tool Invocation Flow - Complete Guide

## 🎯 The Big Picture

When the AI agent calls a tool, here's what happens step-by-step:

```
AI Agent → Tool Function → Schedule on Background Loop → Register & Start
   ↓            ↓                      ↓                        ↓
"book a       @tool                tool_loop            Registry tracks it
 meeting"     decorated            .schedule_task()     Background work starts
              function             
```

---

## 📝 Step-by-Step Flow

### STEP 1: AI Agent Decides to Use a Tool

The LLM (in `ai_agent.py`) generates a response that includes a tool call:

```python
# Inside ai_agent.py, the LLM decides:
# "User wants to book a calendar appointment, I should use book_calendar tool"

# LangChain/LangGraph automatically calls:
book_calendar(date="2024-12-10", time="14:00", title="Team Meeting")
```

**Where this happens**: `src/server/ai_agent.py` in the `generate_response()` stream

**Key point**: The agent doesn't manually invoke tools - LangChain sees the `@tool` decorator and automatically calls the function when the LLM requests it.

---

### STEP 2: Tool Function Executes (Synchronously)

```python
@tool
def book_calendar(date: str, time: str, title: str) -> str:
    """
    This function executes SYNCHRONOUSLY in the agent's thread.
    But we need to do ASYNC work (API calls, etc.)
    """
    
    # Get registry and event loop (singletons)
    registry = get_active_tool_registry()
    tool_loop = get_tool_event_loop()
    
    # Setup threading primitives for sync/async coordination
    cancel_event = threading.Event()
    registration_complete = threading.Event()
    tool_id_holder = {"tool_id": None}
    
    # STEP 3 (next): Define the async registration function
    async def _register_and_start():
        # ... (see next step)
        pass
    
    # STEP 4 (later): Schedule it on background loop
    tool_loop.schedule_task(_register_and_start)
    
    # STEP 5 (later): Wait for registration, then return
    registration_complete.wait(timeout=5.0)
    
    return "Booking in progress..."
```

**Where this happens**: `src/server/example_async_tool.py` (line ~30)

**Key point**: The tool function itself is SYNC but needs to launch ASYNC work.

---

### STEP 3: `_register_and_start` is Defined (Not Yet Called!)

Inside the tool function, we define an **async inner function**:

```python
async def _register_and_start():
    """
    This function will run on the background event loop.
    It registers the tool and starts the actual work.
    """
    try:
        # Register with ActiveToolRegistry
        tool_id = await registry.register_tool(
            tool_name="book_calendar",
            cancel_async_fn=_cancel_booking,  # The cancel hook
            metadata={
                "date": date,
                "time": time,
                "title": title,
                "status": "in_progress"
            },
        )
        
        # Save tool_id so main thread can access it
        tool_id_holder["tool_id"] = tool_id
        
        # Signal that registration is complete
        registration_complete.set()
        
        # Start the actual background work (fire-and-forget)
        asyncio.create_task(_book_appointment_background(tool_id))
        
    except Exception as exc:
        registration_complete.set()
        raise exc
```

**Key point**: This function is just **defined**, not yet executed!

---

### STEP 4: Schedule on Background Event Loop

Now we **schedule** the async function to run on the background loop:

```python
# tool_loop is the ToolEventLoop singleton
# It runs an asyncio event loop in a background thread
if not tool_loop.schedule_task(_register_and_start):
    raise RuntimeError("Failed to schedule tool")
```

**What `schedule_task()` does** (from `tool_event_loop.py`):

```python
def schedule_task(self, coro_fn: Callable[[], Awaitable]) -> bool:
    """
    Schedule an async function to run on the background event loop.
    """
    if not self._loop or not self._loop.is_running():
        return False
    
    # asyncio.run_coroutine_threadsafe bridges threads:
    # - We're in the agent's sync thread
    # - It schedules the coroutine on the background loop's thread
    future = asyncio.run_coroutine_threadsafe(
        coro_fn(),  # Call the function to get the coroutine
        self._loop  # The background event loop
    )
    
    return True
```

**Key point**: `asyncio.run_coroutine_threadsafe()` is the magic that lets a sync thread schedule work on an async loop in another thread!

---

### STEP 5: `_register_and_start` Executes (On Background Thread)

Now the function actually runs:

```
Agent Thread                    Background Event Loop Thread
    |                                      |
    | (1) schedule_task()                  |
    |---------------------------------->   | (2) _register_and_start() starts
    |                                      |     - await registry.register_tool()
    |                                      |     - tool_id_holder["tool_id"] = tool_id
    | (3) registration_complete.wait()    |     - registration_complete.set()
    |     (blocked, waiting...)            |
    |                                      | (4) asyncio.create_task(background_work)
    |                                      |     (fire-and-forget, work continues)
    | (5) wait() unblocks!                 |
    | (6) return to agent                  |
    |                                      | (7) background work runs independently
```

**Key point**: The agent thread waits ONLY for registration, not for the full work to complete!

---

### STEP 6: Tool Returns to Agent

```python
# By now, registration_complete.wait() has unblocked
tool_id = tool_id_holder.get("tool_id")

# Return immediately - work continues in background
return (
    f"✅ Booking '{title}' for {date} at {time}. "
    f"(tracking_id={tool_id[:8]})"
)
```

**Key point**: Agent gets immediate feedback, work continues in background.

---

### STEP 7: Background Work Continues

Meanwhile, in the background thread:

```python
async def _book_appointment_background(tool_id: str):
    """
    This runs independently, even after the tool function returned.
    """
    try:
        # Multi-step workflow
        for step_name, duration in steps:
            if cancel_event.is_set():  # Check for interruption
                print(f"Cancelled at step: {step_name}")
                return
            
            # Do the work (API call, DB query, etc.)
            await asyncio.sleep(duration)
        
        print("Booking complete!")
        
    finally:
        # Always unregister when done
        await registry.unregister_tool(tool_id)
```

**Key point**: This runs until completion OR until `cancel_event` is set by the orchestrator.

---

## 🔄 What Triggers `_register_and_start`?

**Answer**: `tool_loop.schedule_task(_register_and_start)` triggers it!

### Detailed Mechanism:

1. **Tool function calls** `tool_loop.schedule_task(_register_and_start)`
2. **schedule_task()** internally calls:
   ```python
   asyncio.run_coroutine_threadsafe(_register_and_start(), self._loop)
   ```
3. **asyncio.run_coroutine_threadsafe()** puts the coroutine in the background loop's queue
4. **Background event loop** picks it up and executes it
5. **_register_and_start()** runs on the background thread

---

## 🎭 Example: Complete Trace

Let's trace a real example:

```python
# USER: "Book a meeting tomorrow at 2pm about project review"

# 1. Agent (in main thread) calls:
result = book_calendar(
    date="2024-12-04",
    time="14:00",
    title="Project Review"
)

# 2. book_calendar() executes (sync, in agent thread):
#    - Defines _register_and_start
#    - Calls tool_loop.schedule_task(_register_and_start)
#    - Waits for registration_complete.wait()

# 3. Background thread runs _register_and_start:
#    - await registry.register_tool(...)  # Returns tool_id="abc123"
#    - tool_id_holder["tool_id"] = "abc123"
#    - registration_complete.set()  # Unblocks agent thread!
#    - asyncio.create_task(_book_appointment_background("abc123"))

# 4. Agent thread unblocks:
#    - Gets tool_id from tool_id_holder
#    - Returns "✅ Booking 'Project Review'... (tracking_id=abc123)"

# 5. Agent continues streaming response to user:
#    "I've scheduled a meeting for tomorrow at 2pm about project review. 
#     You'll receive a confirmation shortly."

# 6. Background work continues independently:
#    - Validating date/time...
#    - Checking availability...
#    - Reserving slot...
#    - (User interrupts! cancel_event.set() is called)
#    - Cancelled at step: Sending confirmation email
#    - Releasing reserved slot...
#    - await registry.unregister_tool("abc123")
```

---

## 🛠️ How Cancellation Works

When user interrupts:

```python
# In orchestrator.py:
self.ai_agent.cancel()

# In ai_agent.py:
async def cancel(self):
    await self.active_tool_registry.cancel_all_tools()

# In active_tool_registry.py:
async def cancel_all_tools(self):
    for tool_execution in self._active_tools.values():
        if tool_execution.cancel_async_fn:
            await tool_execution.cancel_async_fn()

# Back in example_async_tool.py:
async def _cancel_booking():
    cancel_event.set()  # This makes all the background work stop!
```

---

## 📋 Summary: Who Calls What?

| What | Who Calls It | When |
|------|--------------|------|
| `book_calendar()` | AI agent (LangChain) | When LLM decides to use the tool |
| `_register_and_start()` | `tool_loop.schedule_task()` | Inside `book_calendar()` |
| `_book_appointment_background()` | `asyncio.create_task()` | Inside `_register_and_start()` |
| `_cancel_booking()` | `registry.cancel_all_tools()` | When user interrupts |

---

## 🎓 Key Takeaways

1. **Agent calls the tool** - LangChain automatically invokes `@tool` decorated functions
2. **Tool schedules async work** - Uses `tool_loop.schedule_task()` to bridge sync→async
3. **Background loop runs it** - `_register_and_start()` executes in background thread
4. **Tool returns immediately** - Agent doesn't wait for full work, just registration
5. **Work continues independently** - Until completion or cancellation
6. **Cancellation is cooperative** - `cancel_event` must be checked periodically

---

## 🔍 Where to Look in the Code

1. **Tool invocation**: `src/server/ai_agent.py` (lines ~80-100)
2. **Tool definition**: `src/server/example_async_tool.py` (lines ~30-170)
3. **Background loop**: `src/server/tool_event_loop.py` (lines ~40-80)
4. **Registry**: `src/server/active_tool_registry.py` (lines ~100-200)
5. **Cancellation**: `src/server/orchestrator.py` (lines ~596-620)

