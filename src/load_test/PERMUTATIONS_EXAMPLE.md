# 🎲 How Load Test Uses Permutations & Combinations

## Overview

The load test creates **realistic variety** by randomly selecting from your audio files, simulating how real users would ask different questions in different orders.

---

## 📦 Your Audio File Pool

You have **10 audio files** available:

```
🎤 Normal Queries (2s) - 4 files:
   1. query_2s_balance.wav
   2. query_2s_transactions.wav
   3. query_2s_help.wav
   4. query_2s_services.wav

🔧 Tool Calls (3s) - 2 files:
   5. query_3s_email.wav
   6. query_3s_check_balance.wav

🚨 Interruptions (1.5s) - 2 files:
   7. query_1_5s_interrupt.wav
   8. query_1_5s_another.wav

🎭 False Alarms (0.3s) - 2 files:
   9. noise_0_3s_mhmm.wav
   10. noise_0_3s_uh.wav
```

---

## 🎯 How Randomization Works

### Example: 3 Clients × 3 Requests Each = 9 Total Requests

```
Client 0:
  Request 1 (simple_query)   → 🎲 Randomly picks: query_2s_balance.wav
  Request 2 (tool_call)      → 🎲 Randomly picks: query_3s_email.wav
  Request 3 (simple_query)   → 🎲 Randomly picks: query_2s_services.wav

Client 1:
  Request 1 (simple_query)   → 🎲 Randomly picks: query_2s_transactions.wav
  Request 2 (interruption)   → 🎲 Randomly picks: query_1_5s_interrupt.wav
  Request 3 (simple_query)   → 🎲 Randomly picks: query_2s_help.wav

Client 2:
  Request 1 (tool_call)      → 🎲 Randomly picks: query_3s_check_balance.wav
  Request 2 (false_alarm)    → 🎲 Randomly picks: noise_0_3s_mhmm.wav
  Request 3 (simple_query)   → 🎲 Randomly picks: query_2s_balance.wav (reused!)
```

**Result**: 9 requests using 8 different audio files, some repeated randomly.

---

## 📊 Actual Load Test Output

When you run the test, you'll see which audio file each client uses:

```bash
$ python3 src/load_test/load_test.py --concurrency 3 --requests 3

[Client 0] Request 1/3 (simple_query)
[Client 0] 🎵 Using audio: query_2s_balance.wav
[Client 1] Request 1/3 (simple_query)
[Client 1] 🎵 Using audio: query_2s_transactions.wav
[Client 2] Request 1/3 (tool_call)
[Client 2] 🎵 Using audio: query_3s_email.wav

[Client 0] ⚡ TTFT: 1523.4ms
[Client 1] ⚡ TTFT: 1567.8ms
[Client 2] ⚡ TTFT: 2134.5ms

[Client 0] Request 2/3 (tool_call)
[Client 0] 🎵 Using audio: query_3s_check_balance.wav
[Client 1] Request 2/3 (interruption)
[Client 1] 🎵 Using audio: query_1_5s_interrupt.wav
...
```

---

## 📈 Final Report Shows Distribution

At the end, you'll see exactly how the audio files were distributed:

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
  simple_query: 30
  tool_call: 10
  interruption: 6
  false_alarm: 4

🎵 AUDIO FILES USED (Permutations/Combinations)
  Total unique audio combinations: 10
  Distribution:
    query_2s_balance.wav: 9 times (18.0%)
    query_2s_transactions.wav: 8 times (16.0%)
    query_2s_services.wav: 7 times (14.0%)
    query_2s_help.wav: 6 times (12.0%)
    query_3s_email.wav: 6 times (12.0%)
    query_3s_check_balance.wav: 4 times (8.0%)
    query_1_5s_interrupt.wav: 4 times (8.0%)
    query_1_5s_another.wav: 2 times (4.0%)
    noise_0_3s_mhmm.wav: 2 times (4.0%)
    noise_0_3s_uh.wav: 2 times (4.0%)
```

This shows you used **all 10 audio files** in different combinations, creating **realistic variety**!

---

## 🎲 Mathematical Permutations

### Possible Combinations

With **10 clients × 5 requests = 50 requests**:

- If requests are: 30 simple, 10 tool, 6 interruption, 4 false alarm
- Simple queries can pick from **4 files** (random each time)
- Tool calls can pick from **2 files** (random each time)
- Interruptions can pick from **2 files** (random each time)
- False alarms can pick from **2 files** (random each time)

**Theoretical unique sequences**: 
```
4^30 × 2^10 × 2^6 × 2^4 = Billions of possible combinations!
```

Each test run will produce a **different distribution** = realistic load testing!

---

## 🌟 Why This Is Professional

### ✅ Real-World Simulation
- **Real users don't all ask the same question**
- Different queries stress different code paths
- Randomization reveals edge cases

### ✅ Comprehensive Coverage
- Every test run exercises different combinations
- All audio files get tested over time
- Prevents "testing bias" (always using same sample)

### ✅ Statistical Validity
- Large sample size (50+ requests) averages out randomness
- Distribution shows if certain queries fail more often
- Identifies performance differences between query types

---

## 🎯 Example Use Cases

### 1. Find Slow Queries
```
🎵 AUDIO FILES USED
  Distribution:
    query_2s_balance.wav: 12 times (avg TTFT: 1.2s) ✅ Fast
    query_3s_email.wav: 10 times (avg TTFT: 3.5s) ⚠️ Slow!
```
→ Tool calls are slower (expected, but now you have proof!)

### 2. Identify Problematic Audio
```
🎵 AUDIO FILES USED
  Distribution:
    query_2s_transactions.wav: 8 times (6 failed) ❌
    query_2s_help.wav: 7 times (0 failed) ✅
```
→ "transactions" query might have transcription issues

### 3. Balance Testing
```
🎵 AUDIO FILES USED
  Total unique audio combinations: 10
```
→ Confirms all audio files are being tested

---

## 🔧 Controlling Distribution

Want to test specific scenarios more heavily?

### More Interruptions
```bash
python3 src/load_test/load_test.py \
  --interruptions 0.7 \
  --simple 0.2 \
  --tools 0.1
```
Result: More `query_1_5s_*.wav` files will be used

### Only Tool Calls
```bash
python3 src/load_test/load_test.py \
  --tools 1.0 \
  --simple 0.0 \
  --interruptions 0.0
```
Result: Only `query_3s_*.wav` files will be used

---

## 🎉 Summary

**Yes, this is professional load testing!**

✅ **Random selection** from audio pool  
✅ **Permutations & combinations** create variety  
✅ **Tracks distribution** to show coverage  
✅ **Simulates real users** asking different questions  
✅ **Statistical validity** with large sample sizes  

This approach is used by companies like:
- Netflix (testing streaming endpoints)
- Uber (testing ride request patterns)
- Amazon (testing product search queries)

Your load test now follows **industry best practices**! 🚀

