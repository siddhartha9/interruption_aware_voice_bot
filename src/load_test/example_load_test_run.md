# Load Test Example Run

## Example 1: Basic Load Test (10 concurrent clients, 5 requests each)

### Command:
```bash
python3 src/load_test/load_test.py --concurrency 10 --requests 5
```

### Live Output During Test:
```
🚀 Starting load test:
  Server: ws://localhost:8000/ws
  Concurrency: 10
  Requests per client: 5
  Total requests: 50
  Scenarios: {'simple_query': 0.6, 'tool_call': 0.2, 'interruption': 0.1, 'false_alarm': 0.1}

[Client 0] ✓ Connected in 0.023s
[Client 1] ✓ Connected in 0.025s
[Client 2] ✓ Connected in 0.024s
[Client 3] ✓ Connected in 0.026s
[Client 4] ✓ Connected in 0.023s
[Client 5] ✓ Connected in 0.027s
[Client 6] ✓ Connected in 0.024s
[Client 7] ✓ Connected in 0.025s
[Client 8] ✓ Connected in 0.026s
[Client 9] ✓ Connected in 0.023s

[Client 0] Request 1/5 (simple_query)
[Client 1] Request 1/5 (tool_call)
[Client 2] Request 1/5 (simple_query)
[Client 3] Request 1/5 (interruption)
[Client 3] 🎭 Interruption scenario starting...
[Client 3]   → Sent initial query
[Client 4] Request 1/5 (simple_query)
[Client 5] Request 1/5 (false_alarm)
[Client 5] 🎭 False alarm scenario...
[Client 6] Request 1/5 (simple_query)
[Client 7] Request 1/5 (simple_query)
[Client 8] Request 1/5 (tool_call)
[Client 9] Request 1/5 (simple_query)

[Client 0] ⚡ TTFT: 1456.3ms
[Client 2] ⚡ TTFT: 1512.7ms
[Client 4] ⚡ TTFT: 1489.1ms
[Client 3]   ✓ Agent started responding
[Client 3]   🚨 Interrupting with new query...
[Client 6] ⚡ TTFT: 1534.2ms
[Client 7] ⚡ TTFT: 1498.5ms
[Client 9] ⚡ TTFT: 1523.8ms
[Client 5]   → Sent speech_start (false alarm)
[Client 5]   → False alarm complete (should resume)
[Client 1] ⚡ TTFT: 2145.6ms
[Client 8] ⚡ TTFT: 2198.3ms

[Client 0] 🏁 Total: 4523.2ms (12 chunks)
[Client 2] 🏁 Total: 4687.1ms (13 chunks)
[Client 4] 🏁 Total: 4612.8ms (11 chunks)
[Client 6] 🏁 Total: 4754.3ms (14 chunks)
[Client 7] 🏁 Total: 4598.2ms (12 chunks)
[Client 9] 🏁 Total: 4634.7ms (13 chunks)
[Client 3] ⚡ TTFT: 1678.9ms
[Client 3] 🏁 Total: 5234.1ms (15 chunks)
[Client 3]   ✓ Interruption handled successfully
[Client 5] ⚡ TTFT: 1823.4ms
[Client 5] 🏁 Total: 5456.2ms (14 chunks)
[Client 1] 🏁 Total: 6234.5ms (18 chunks)
[Client 8] 🏁 Total: 6387.1ms (19 chunks)

[Client 0] Request 2/5 (simple_query)
[Client 1] Request 2/5 (simple_query)
[Client 2] Request 2/5 (false_alarm)
[Client 2] 🎭 False alarm scenario...
...
[continues for remaining requests]
...

[Client 9] ✓ Session complete
[Client 8] ✓ Session complete
[Client 7] ✓ Session complete
[Client 6] ✓ Session complete
[Client 5] ✓ Session complete
[Client 4] ✓ Session complete
[Client 3] ✓ Session complete
[Client 2] ✓ Session complete
[Client 1] ✓ Session complete
[Client 0] ✓ Session complete

✅ Load test complete in 47.83s
```

### Final Performance Report:
```
================================================================================
🎯 LOAD TEST PERFORMANCE REPORT
================================================================================

📊 SUMMARY
  Total Requests:      50
  ✅ Successful:       48 (96.0%)
  ❌ Failed:           2
  🔌 Connection Errors: 0

📋 REQUEST TYPES
  simple_query: 31
  tool_call: 10
  interruption: 5
  false_alarm: 4

🔌 CONNECTION LATENCY
     Min:      23.0ms  (0.023s)
     Mean:     24.8ms  (0.025s)
     Median:   24.5ms  (0.024s)
     P95:      27.0ms  (0.027s)
     P99:      27.0ms  (0.027s)
     Max:      27.0ms  (0.027s)

⚡ TIME TO FIRST TOKEN (TTFT)
   📍 Definition: Time from speech_end → first audio chunk received
     Min:    1434.0ms  (1.434s)
     Mean:   1823.5ms  (1.824s)
     Median: 1789.0ms  (1.789s)
     P95:    2456.0ms  (2.456s)
     P99:    2598.0ms  (2.598s)
     Max:    2645.0ms  (2.645s)

🏁 TOTAL RESPONSE TIME
   📍 Definition: Time from speech_end → response fully delivered
     Min:    4512.0ms  (4.512s)
     Mean:   5234.7ms  (5.235s)
     Median: 5123.0ms  (5.123s)
     P95:    6789.0ms  (6.789s)
     P99:    7234.0ms  (7.234s)
     Max:    7456.0ms  (7.456s)

================================================================================
```

---

## Example 2: Interruption-Heavy Test

### Command:
```bash
python3 src/load_test/load_test.py --concurrency 10 --requests 3 \
  --interruptions 0.5 --false-alarms 0.3 --simple 0.2 --tools 0.0
```

### What You'll See:
```
🚀 Starting load test:
  Server: ws://localhost:8000/ws
  Concurrency: 10
  Requests per client: 3
  Total requests: 30
  Scenarios: {'simple_query': 0.2, 'tool_call': 0.0, 'interruption': 0.5, 'false_alarm': 0.3}

[Client 0] ✓ Connected in 0.024s
[Client 1] ✓ Connected in 0.025s
[Client 2] ✓ Connected in 0.023s
[Client 3] ✓ Connected in 0.026s
[Client 4] ✓ Connected in 0.024s
[Client 5] ✓ Connected in 0.025s
[Client 6] ✓ Connected in 0.023s
[Client 7] ✓ Connected in 0.027s
[Client 8] ✓ Connected in 0.024s
[Client 9] ✓ Connected in 0.025s

[Client 0] Request 1/3 (interruption)
[Client 0] 🎭 Interruption scenario starting...
[Client 0]   → Sent initial query
[Client 1] Request 1/3 (false_alarm)
[Client 1] 🎭 False alarm scenario...
[Client 2] Request 1/3 (interruption)
[Client 2] 🎭 Interruption scenario starting...
[Client 2]   → Sent initial query
[Client 3] Request 1/3 (simple_query)
[Client 4] Request 1/3 (interruption)
[Client 4] 🎭 Interruption scenario starting...
[Client 4]   → Sent initial query
[Client 5] Request 1/3 (false_alarm)
[Client 5] 🎭 False alarm scenario...
[Client 6] Request 1/3 (interruption)
[Client 6] 🎭 Interruption scenario starting...
[Client 6]   → Sent initial query
[Client 7] Request 1/3 (false_alarm)
[Client 7] 🎭 False alarm scenario...
[Client 8] Request 1/3 (interruption)
[Client 8] 🎭 Interruption scenario starting...
[Client 8]   → Sent initial query
[Client 9] Request 1/3 (interruption)
[Client 9] 🎭 Interruption scenario starting...
[Client 9]   → Sent initial query

[Client 0]   ✓ Agent started responding
[Client 0]   🚨 Interrupting with new query...
[Client 2]   ✓ Agent started responding
[Client 2]   🚨 Interrupting with new query...
[Client 4]   ✓ Agent started responding
[Client 4]   🚨 Interrupting with new query...
[Client 6]   ✓ Agent started responding
[Client 6]   🚨 Interrupting with new query...
[Client 8]   ✓ Agent started responding
[Client 8]   🚨 Interrupting with new query...
[Client 9]   ✓ Agent started responding
[Client 9]   🚨 Interrupting with new query...
[Client 3] ⚡ TTFT: 1523.4ms
[Client 1]   → Sent speech_start (false alarm)
[Client 1]   → False alarm complete (should resume)
[Client 5]   → Sent speech_start (false alarm)
[Client 5]   → False alarm complete (should resume)
[Client 7]   → Sent speech_start (false alarm)
[Client 7]   → False alarm complete (should resume)

[Client 0] ⚡ TTFT: 1678.2ms
[Client 2] ⚡ TTFT: 1689.5ms
[Client 4] ⚡ TTFT: 1712.8ms
[Client 6] ⚡ TTFT: 1734.1ms
[Client 8] ⚡ TTFT: 1698.3ms
[Client 9] ⚡ TTFT: 1723.9ms
[Client 1] ⚡ TTFT: 1845.6ms
[Client 5] ⚡ TTFT: 1867.2ms
[Client 7] ⚡ TTFT: 1889.4ms
[Client 3] 🏁 Total: 4634.7ms (13 chunks)

[Client 0] 🏁 Total: 5234.1ms (15 chunks)
[Client 0]   ✓ Interruption handled successfully
[Client 2] 🏁 Total: 5298.7ms (14 chunks)
[Client 2]   ✓ Interruption handled successfully
[Client 4] 🏁 Total: 5412.3ms (16 chunks)
[Client 4]   ✓ Interruption handled successfully
[Client 6] 🏁 Total: 5387.9ms (15 chunks)
[Client 6]   ✓ Interruption handled successfully
[Client 8] 🏁 Total: 5456.2ms (15 chunks)
[Client 8]   ✓ Interruption handled successfully
[Client 9] 🏁 Total: 5523.8ms (16 chunks)
[Client 9]   ✓ Interruption handled successfully
[Client 1] 🏁 Total: 5789.1ms (14 chunks)
[Client 5] 🏁 Total: 5834.5ms (15 chunks)
[Client 7] 🏁 Total: 5923.7ms (14 chunks)

[Client 0] Request 2/3 (false_alarm)
[Client 1] Request 2/3 (interruption)
...

✅ Load test complete in 28.45s

================================================================================
🎯 LOAD TEST PERFORMANCE REPORT
================================================================================

📊 SUMMARY
  Total Requests:      30
  ✅ Successful:       29 (96.7%)
  ❌ Failed:           1
  🔌 Connection Errors: 0

📋 REQUEST TYPES
  simple_query: 6
  tool_call: 0
  interruption: 15
  false_alarm: 9

⚡ TIME TO FIRST TOKEN (TTFT)
   📍 Definition: Time from speech_end → first audio chunk received
     Min:    1523.0ms  (1.523s)
     Mean:   1756.3ms  (1.756s)
     Median: 1734.0ms  (1.734s)
     P95:    1923.0ms  (1.923s)
     P99:    1989.0ms  (1.989s)
     Max:    2012.0ms  (2.012s)

🏁 TOTAL RESPONSE TIME
   📍 Definition: Time from speech_end → response fully delivered
     Min:    4634.0ms  (4.634s)
     Mean:   5456.8ms  (5.457s)
     Median: 5412.0ms  (5.412s)
     P95:    6123.0ms  (6.123s)
     P99:    6234.0ms  (6.234s)
     Max:    6345.0ms  (6.345s)

================================================================================
```

---

## Example 3: Quick Sanity Check (1 client, 1 request)

### Command:
```bash
python3 src/load_test/load_test.py --concurrency 1 --requests 1
```

### Output:
```
🚀 Starting load test:
  Server: ws://localhost:8000/ws
  Concurrency: 1
  Requests per client: 1
  Total requests: 1
  Scenarios: {'simple_query': 0.6, 'tool_call': 0.2, 'interruption': 0.1, 'false_alarm': 0.1}

[Client 0] ✓ Connected in 0.024s
[Client 0] Request 1/1 (simple_query)
[Client 0] ⚡ TTFT: 1523.4ms
[Client 0] 🏁 Total: 4634.7ms (13 chunks)
[Client 0] ✓ Session complete

✅ Load test complete in 5.89s

================================================================================
🎯 LOAD TEST PERFORMANCE REPORT
================================================================================

📊 SUMMARY
  Total Requests:      1
  ✅ Successful:       1 (100.0%)
  ❌ Failed:           0
  🔌 Connection Errors: 0

📋 REQUEST TYPES
  simple_query: 1

🔌 CONNECTION LATENCY
     Min:      24.0ms  (0.024s)
     Mean:     24.0ms  (0.024s)
     Median:   24.0ms  (0.024s)
     P95:      24.0ms  (0.024s)
     P99:      24.0ms  (0.024s)
     Max:      24.0ms  (0.024s)

⚡ TIME TO FIRST TOKEN (TTFT)
   📍 Definition: Time from speech_end → first audio chunk received
     Min:    1523.4ms  (1.523s)
     Mean:   1523.4ms  (1.523s)
     Median: 1523.4ms  (1.523s)
     P95:    1523.4ms  (1.523s)
     P99:    1523.4ms  (1.523s)
     Max:    1523.4ms  (1.523s)

🏁 TOTAL RESPONSE TIME
   📍 Definition: Time from speech_end → response fully delivered
     Min:    4634.7ms  (4.635s)
     Mean:   4634.7ms  (4.635s)
     Median: 4634.7ms  (4.635s)
     P95:    4634.7ms  (4.635s)
     P99:    4634.7ms  (4.635s)
     Max:    4634.7ms  (4.635s)

================================================================================
```

---

## Key Things to Observe

### ✅ Good Performance Indicators:
- **TTFT < 2s**: System feels responsive
- **Success rate > 95%**: Robust under load
- **P95 < 3s**: Most requests are fast
- **Interruptions handled**: No crashes or hangs

### ⚠️ Warning Signs:
- **TTFT > 3s**: Users will notice lag
- **Success rate < 90%**: System struggling
- **Connection errors**: Server overloaded
- **Failed interruptions**: State management issues

### 🔧 What Gets Tested:
1. **Simple queries**: Basic STT → LLM → TTS pipeline
2. **Tool calls**: Async tool execution + longer responses
3. **Real interruptions**: Mid-response cancellation + recovery
4. **False alarms**: Playback pause/resume logic

