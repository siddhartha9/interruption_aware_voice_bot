# Load Testing & Performance Benchmarking Guide

## Overview

The `load_test.py` script simulates multiple concurrent voice bot sessions to measure performance and latency under load.

## Prerequisites

```bash
pip install websockets
```

## Quick Start

### 1. Start the Server

```bash
./start.sh
```

Wait for the server to be ready (should show "Server ready on port 8000").

### 2. Run Load Test

#### Basic Test (10 concurrent connections)
```bash
python3 load_test.py --concurrency 10 --requests 5
```

#### High Concurrency Test (20+ connections)
```bash
python3 load_test.py --concurrency 20 --requests 10
```

#### Stress Test (50+ connections)
```bash
python3 load_test.py --concurrency 50 --requests 3
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--server` | WebSocket server URL | `ws://localhost:8000/ws` |
| `--concurrency` | Number of concurrent connections | `10` |
| `--requests` | Requests per client session | `5` |
| `--simple` | Weight for simple queries (0-1) | `0.6` |
| `--tools` | Weight for tool call queries (0-1) | `0.2` |
| `--interruptions` | Weight for interruption scenarios (0-1) | `0.1` |
| `--false-alarms` | Weight for false alarm scenarios (0-1) | `0.1` |

## Test Scenarios

### 1. Simple Query ✅
**What it tests**: Basic query-response flow
- Sends a 2-second audio chunk (simulated speech)
- Waits for complete agent response
- Measures TTFT and total response time
- **Use case**: Normal conversation flow

### 2. Tool Call 🔧
**What it tests**: Async tool execution under load
- Sends a 3-second audio chunk
- Extended timeout (45s) to account for async tool execution
- Tracks tool call success rate
- **Use case**: Complex queries requiring external operations (checking balance, sending emails)

### 3. Real Interruption 🚨
**What it tests**: Realistic mid-response interruption handling
- **Step 1**: Sends initial query (2s audio)
- **Step 2**: Waits for agent to START responding (receives first audio chunk)
- **Step 3**: Interrupts mid-response (0.3-0.8s delay after first audio)
- **Step 4**: Sends new query (1.5s audio)
- **Step 5**: Measures recovery time for new response
- **Use case**: User cuts off agent to ask a new question

### 4. False Alarm 🎭
**What it tests**: Noise detection and playback resume logic
- **Step 1**: Sends initial query (2s audio)
- **Step 2**: Waits for agent to START responding
- **Step 3**: Sends `speech_start` (pretends to interrupt)
- **Step 4**: Sends very short audio (300ms - recognized as noise)
- **Step 5**: Expects system to resume original playback
- **Use case**: User says "mhmm" or makes noise but doesn't actually interrupt

## Metrics Tracked

### 🎯 Key Performance Metrics

#### ⚡ Time to First Token (TTFT)
**Definition**: Time from `speech_end` → first audio chunk received

This metric captures the **perceived responsiveness** of the system:
- Includes: STT processing + LLM first token + TTS synthesis + network
- **Critical for UX**: Users notice delays > 1 second
- Target: < 1.5s (excellent), < 2.5s (acceptable)

#### 🏁 Total Response Time
**Definition**: Time from `speech_end` → response fully delivered

This metric captures the **complete conversation cycle**:
- Includes: Full agent response generation + all TTS chunks
- Depends on: Response length, complexity, tool calls
- Target: < 5s for short responses, < 10s for long responses

### Additional Metrics
- **Connection Time**: Time to establish WebSocket connection
- **Success Rate**: Percentage of successful requests vs failures
- **Request Type Distribution**: Breakdown by scenario type

### Statistics
For each metric, the report shows:
- **Min**: Fastest request
- **Mean**: Average
- **Median**: 50th percentile
- **P95**: 95th percentile (95% of requests faster than this)
- **P99**: 99th percentile (99% of requests faster than this)
- **Max**: Slowest request

### Success/Failure Tracking
- Successful requests
- Failed requests
- Connection errors
- Request type breakdown

## Example Output

```
🚀 Starting load test:
  Server: ws://localhost:8000/ws
  Concurrency: 10
  Requests per client: 5
  Total requests: 50
  Scenarios: {'simple_query': 0.7, 'tool_call': 0.2, 'interruption': 0.1}

[Client 0] ✓ Connected in 0.023s
[Client 1] ✓ Connected in 0.025s
...
[Client 0] Request 1/5 (simple_query)
...

✅ Load test complete in 45.23s

================================================================================
🎯 LOAD TEST PERFORMANCE REPORT
================================================================================

📊 SUMMARY
  Total Requests:      50
  ✅ Successful:       48 (96.0%)
  ❌ Failed:           2
  🔌 Connection Errors: 0

📋 REQUEST TYPES
  simple_query: 35
  tool_call: 10
  interruption: 5

🔌 CONNECTION LATENCY
     Min:      20.0ms  (0.020s)
     Mean:     25.0ms  (0.025s)
     Median:   24.0ms  (0.024s)
     P95:      30.0ms  (0.030s)
     P99:      35.0ms  (0.035s)
     Max:      40.0ms  (0.040s)

⚡ TIME TO FIRST TOKEN (TTFT)
   📍 Definition: Time from speech_end → first audio chunk received
     Min:    1234.0ms  (1.234s)
     Mean:   2456.0ms  (2.456s)
     Median: 2300.0ms  (2.300s)
     P95:    3500.0ms  (3.500s)
     P99:    4200.0ms  (4.200s)
     Max:    5100.0ms  (5.100s)

🏁 TOTAL RESPONSE TIME
   📍 Definition: Time from speech_end → response fully delivered
     Min:    3456.0ms  (3.456s)
     Mean:   5678.0ms  (5.678s)
     Median: 5500.0ms  (5.500s)
     P95:    7800.0ms  (7.800s)
     P99:    9100.0ms  (9.100s)
     Max:   10500.0ms  (10.500s)

================================================================================
```

## Performance Targets

### 🎯 Recommended Targets (Low Load, 1-10 concurrent)
- **TTFT Mean**: < 1.5s (excellent responsiveness)
- **TTFT P95**: < 2.5s (95% of requests feel snappy)
- **Total Response Time Mean**: < 5s for short responses
- **Connection Time**: < 100ms
- **Success Rate**: > 99%

### ⚠️ Acceptable Under Load (>20 concurrent)
- **TTFT Mean**: < 2.5s
- **TTFT P95**: < 4s
- **Total Response Time Mean**: < 8s for short responses
- **Success Rate**: > 95%

### 🚨 Performance Issues (Action Required)
- **TTFT Mean**: > 3s (users will notice lag)
- **TTFT P99**: > 5s (unacceptable for real-time conversation)
- **Success Rate**: < 90%

## Troubleshooting

### High Connection Errors
- Check if server is running
- Verify WebSocket URL is correct
- Check firewall/network settings

### High Failure Rate
- Server may be overloaded
- Check server logs for errors
- Reduce concurrency or increase server resources

### Slow Response Times
- Check STT/LLM API rate limits
- Verify network latency to external APIs
- Consider caching or optimizations

## Advanced Usage

### Focus on Interruption Testing
Test interruption and false alarm handling:
```bash
python3 load_test.py --concurrency 10 --interruptions 0.5 --false-alarms 0.3 --simple 0.2 --tools 0.0
```

### Pure Interruption Stress Test
Only test interruptions:
```bash
python3 load_test.py --simple 0.0 --tools 0.0 --interruptions 1.0 --false-alarms 0.0 --concurrency 5
```

### False Alarm Focus
Test playback resume logic:
```bash
python3 load_test.py --simple 0.2 --tools 0.0 --interruptions 0.2 --false-alarms 0.6 --concurrency 10
```

### Tool-Heavy Workload
Focus more on tool calls:
```bash
python3 load_test.py --simple 0.3 --tools 0.6 --interruptions 0.1 --false-alarms 0.0
```

### Quick Sanity Check
```bash
python3 load_test.py --concurrency 1 --requests 1
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Performance Test
  run: |
    ./start.sh &
    sleep 10
    python3 load_test.py --concurrency 10 --requests 3
    if [ $? -ne 0 ]; then exit 1; fi
```

### Performance Regression Detection
Set thresholds and fail if metrics exceed them:
```bash
# Run test and parse output
python3 load_test.py > results.txt

# Check if P95 latency exceeds threshold
if grep "P95:" results.txt | awk '{print $2}' | grep -E '[5-9]\.[0-9]+s'; then
  echo "P95 latency too high!"
  exit 1
fi
```

## Notes

- The script uses **simulated audio** (zeros) to avoid dependencies on actual audio files
- Real STT processing time depends on Deepgram API performance and audio complexity
- Tool calls add significant latency due to async execution and LLM processing
- Interruption scenarios test the orchestrator's state management under load

## Future Enhancements

- [ ] Add real audio file support
- [ ] Export metrics to JSON/CSV for analysis
- [ ] Integration with monitoring tools (Prometheus, Grafana)
- [ ] Streaming metrics during test execution
- [ ] Configurable timeout values per scenario
- [ ] Add TTS latency tracking when server exposes it

