# Tool Unregistration - How Tools Clean Up

## 🎯 The Key Answer

**Tools unregister themselves automatically when they finish** - both sync and async tools. This happens in a `finally` block to guarantee cleanup even if errors occur.

---

## 📋 Unregistration Pattern by Tool Type

### 1. **Synchronous Tools** (like `check_account_balance`)

```python
def _run_sync_tool_with_registry(
    tool_name: str,
    work_coro_factory: Callable[[threading.Event, Optional[Dict]], Awaitable[str]],
    metadata: Optional[Dict] = None,
) -> str:
    async def _execute():
        tool_id: Optional[str] = None
        try:
            # Register
            tool_id = await registry.register_tool(
                tool_name=tool_name,
                cancel_async_fn=_cancel,
                metadata=metadata or {},
            )
            # Do the work
            result = await work_coro_factory(cancel_event, {"tool_id": tool_id})
            result_holder["result"] = result
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            # 🔑 UNREGISTER HERE - Always runs!
            if tool_id is not None:
                await registry.unregister_tool(tool_id)  # ← UNREGISTRATION
            done_event.set()
    
    # Schedule and wait
    tool_loop.schedule_task(_execute)
    done_event.wait()
    return result_holder.get("result", "")
```

**When it unregisters**: Immediately after the background work completes (success, error, or cancellation).

---

### 2. **Asynchronous Tools** (like `book_calendar`, `email_bank_statement`)

```python
async def _book_appointment_background(tool_id: str):
    """Background work function."""
    try:
        # Step 1: Validate date/time
        await asyncio.sleep(0.5)
        if cancel_event.is_set():
            return  # Early exit
        
        # Step 2: Check availability
        await asyncio.sleep(1.0)
        if cancel_event.is_set():
            return  # Early exit
        
        # Step 3: Reserve slot
        await asyncio.sleep(0.8)
        if cancel_event.is_set():
            return  # Early exit
        
        # Step 4: Send confirmation
        await asyncio.sleep(1.2)
        if cancel_event.is_set():
            return  # Early exit
        
        # Step 5: Update calendar
        await asyncio.sleep(0.5)
        
        print("✅ Booking complete!")
        
    except Exception as exc:
        print(f"❌ Error: {exc}")
    finally:
        # 🔑 UNREGISTER HERE - Always runs!
        await registry.unregister_tool(tool_id)  # ← UNREGISTRATION
        print(f"Unregistered tool {tool_id}")
```

**When it unregisters**: After the background work function completes (success, error, or cancellation).

---

## 🔄 Complete Flow with Unregistration

### For **Sync Tools**:

```
User calls check_account_balance()
    ↓
tool_loop.schedule_task(_execute)  ← Schedule background work
    ↓
_execute() runs on background thread
    ├── register_tool()           ← Register
    ├── work_coro_factory()       ← Do work
    └── unregister_tool()         ← ALWAYS UNREGISTER (finally block)
    ↓
done_event.set()                  ← Signal completion
    ↓
Main thread continues             ← Tool function returns result
```

### For **Async Tools**:

```
User calls book_calendar()
    ↓
_register_and_start() scheduled
    ↓
register_tool()                   ← Register
    ↓
asyncio.create_task(background_work)  ← Start background work
    ↓
Tool function returns immediately   ← User gets immediate feedback
    ↓
Background work runs independently
    ├── Step 1: Validate
    ├── Step 2: Check availability
    ├── Step 3: Reserve slot
    ├── Step 4: Send confirmation
    ├── Step 5: Update calendar
    └── finally: unregister_tool()   ← ALWAYS UNREGISTER
```

---

## 🛡️ Why `finally` Block Is Critical

```python
async def _book_appointment_background(tool_id: str):
    try:
        # Work that might fail
        await api_call_that_might_fail()
    except Exception as exc:
        print(f"Error: {exc}")
        # Handle error but DON'T return early
    finally:
        # 🔑 THIS ALWAYS RUNS - even if there was an exception
        await registry.unregister_tool(tool_id)
```

**Guarantees**:
- ✅ Unregisters on success
- ✅ Unregisters on error
- ✅ Unregisters on cancellation
- ✅ Unregisters even if you `return` early from `try` block

---

## 🎭 What Happens in `unregister_tool()`?

```python
# In active_tool_registry.py
async def unregister_tool(self, tool_id: str) -> bool:
    """Remove a tool from the registry."""
    if tool_id in self._active_tools:
        tool_execution = self._active_tools[tool_id]
        tool_execution.is_complete = True
        del self._active_tools[tool_id]
        print(f"[Registry] Unregistered tool {tool_id}")
        return True
    return False
```

**Effects**:
- Tool removed from `_active_tools` dict
- `is_complete = True`
- Tool no longer appears in `get_active_tools()`
- Tool can no longer be cancelled (since it's done)

---

## 🔍 Checking if Tools Are Properly Unregistering

```python
# Debug: Check active tools
from src.server.programmatic_tool_caller import get_active_tool_status

status = await get_active_tool_status()
print(f"Active tools: {status['count']}")
for tool in status['tools']:
    print(f"  - {tool['name']} (running {tool['duration']}s)")
```

**Expected**: After tool completes, it should disappear from this list.

---

## 🚨 What If Unregistration Fails?

**Very rare**, but if it happens:

1. **Tool stays in registry** indefinitely
2. **Appears in `get_active_tools()`** forever
3. **Can't be cancelled** (but it's already done)
4. **Memory leak** (one dict entry)

**Prevention**: Always use `finally` blocks, never skip unregistration.

---

## 🎓 Summary

### Sync Tools:
- Unregister in `_execute()`'s `finally` block
- Happens immediately after work completes
- Main thread waits for unregistration

### Async Tools:
- Unregister in background work function's `finally` block
- Happens after background work completes
- Main thread doesn't wait (fire-and-forget)

### Both Use:
- `finally` blocks for guaranteed cleanup
- `await registry.unregister_tool(tool_id)` call
- Same registry mechanism

**Bottom line**: Tools clean up after themselves automatically! 🧹✨
