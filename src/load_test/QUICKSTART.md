# 🚀 Load Test Quick Start Guide

## ✅ Setup Complete!

Your load test is now configured with **real audio samples** generated using Mac's text-to-speech.

### What We Generated:

```
✅ 10 real audio files in audio_samples/:
   - 4 × 2-second queries (normal conversation)
   - 2 × 3-second queries (tool calls)
   - 2 × 1.5-second queries (interruptions)
   - 2 × 0.3-second audio (false alarms)
```

---

## 🎯 Running the Load Test

### 1. Start Your Server

```bash
cd /Users/suman/Documents/voice_bot
./start.sh
```

Wait for:
```
✅ Server ready on port 8000
WebSocket endpoint: ws://localhost:8000/ws
```

### 2. Run Load Test (in a new terminal)

```bash
cd /Users/suman/Documents/voice_bot

# Basic test: 10 concurrent users, 5 queries each
python3 src/load_test/load_test.py --concurrency 10 --requests 5
```

### 3. Watch the Results!

You should now see **REAL responses**:

```
[Client 0] ⚡ TTFT: 1456.3ms        ← Real time to first token!
[Client 0] 🏁 Total: 4523.2ms (12 chunks)
[Client 1] ⚡ TTFT: 1512.7ms
[Client 2] ⚡ TTFT: 1489.1ms
...

================================================================================
🎯 LOAD TEST PERFORMANCE REPORT
================================================================================

📊 SUMMARY
  Total Requests:      50
  ✅ Successful:       45 (90.0%)     ← Success!
  ❌ Failed:           5
  🔌 Connection Errors: 0

⚡ TIME TO FIRST TOKEN (TTFT)
     Mean:   1523.5ms  (1.524s)      ← Real performance metrics!
     P95:    2156.0ms  (2.156s)
```

---

## 🎭 Test Different Scenarios

### Test Interruptions Heavily
```bash
python3 src/load_test/load_test.py \
  --concurrency 10 \
  --requests 5 \
  --interruptions 0.5 \
  --false-alarms 0.3 \
  --simple 0.2
```

### Stress Test (High Load)
```bash
python3 src/load_test/load_test.py \
  --concurrency 50 \
  --requests 3
```

### Quick Sanity Check
```bash
python3 src/load_test/load_test.py \
  --concurrency 1 \
  --requests 1
```

---

## ⏱️ Response Timing

The load test **waits at least 2 seconds** before checking for responses. This gives the server time to:
1. Process STT (Speech-to-Text) with Deepgram
2. Generate LLM response with Groq
3. Synthesize TTS (Text-to-Speech)
4. Start streaming audio back

This prevents false timeouts and provides accurate TTFT (Time to First Token) measurements.

## 📊 What Audio Gets Used

The load test **automatically selects** appropriate audio files:

| Scenario | Duration | Audio Files Used |
|----------|----------|------------------|
| **Simple Query** | 2s | `query_2s_balance.wav`, `query_2s_transactions.wav`, etc. |
| **Tool Call** | 3s | `query_3s_email.wav`, `query_3s_check_balance.wav` |
| **Interruption** | 1.5s | `query_1_5s_interrupt.wav`, `query_1_5s_another.wav` |
| **False Alarm** | 0.3s | `noise_0_3s_mhmm.wav`, `noise_0_3s_uh.wav` |

The test **randomly picks** from available files to simulate realistic variation.

---

## 🔧 Regenerate Audio (if needed)

If you want to add more audio samples:

```bash
cd /Users/suman/Documents/voice_bot/src/load_test
./generate_audio_samples.sh
```

Or manually add your own:
```bash
# Record with Mac's say command
say "Your custom query here" -o audio_samples/query_2s_custom.wav \
  --data-format=LEI16@16000 --channels=1
```

---

## 🎯 Expected Results

### ✅ Good Performance:
- **Success Rate**: > 90%
- **TTFT Mean**: < 2s
- **TTFT P95**: < 3s
- No connection errors

### ⚠️ Needs Optimization:
- **Success Rate**: 70-90%
- **TTFT Mean**: 2-3s
- **TTFT P95**: 3-5s

### 🚨 Performance Issues:
- **Success Rate**: < 70%
- **TTFT Mean**: > 3s
- **TTFT P99**: > 5s
- Connection errors

---

## 🐛 Troubleshooting

### Still Getting 0% Success Rate?

**Check 1**: Audio files exist
```bash
ls -lh src/load_test/audio_samples/
# Should show 10 .wav files
```

**Check 2**: Server is running
```bash
curl http://localhost:8000
# Should return server response
```

**Check 3**: Deepgram API key is set
```bash
echo $DEEPGRAM_API_KEY
# Should show your API key
```

**Check 4**: Check server logs for errors
```
Look for:
- Deepgram errors
- STT processing errors
- WebSocket disconnections
```

### Fallback to Synthetic Audio Warning?

If you see:
```
[Client 0] ⚠️ No real audio found, using synthetic (expect failures)
```

This means the audio files weren't found. Run:
```bash
cd /Users/suman/Documents/voice_bot/src/load_test
./generate_audio_samples.sh
```

---

## 📈 Performance Benchmarking

### Baseline Test (Low Load)
```bash
# Run this first to establish baseline
python3 src/load_test/load_test.py --concurrency 5 --requests 3
```

### Progressive Load Increase
```bash
# Gradually increase load to find limits
python3 src/load_test/load_test.py --concurrency 10 --requests 5
python3 src/load_test/load_test.py --concurrency 20 --requests 5
python3 src/load_test/load_test.py --concurrency 50 --requests 3
python3 src/load_test/load_test.py --concurrency 100 --requests 2
```

Compare metrics at each level to find your server's capacity!

---

## 🎉 You're All Set!

Your load testing setup is complete. Run the test and you should now see **real performance metrics** with actual TTFT measurements and success rates!

**Next Step**: Start your server and run the first test:

```bash
# Terminal 1
./start.sh

# Terminal 2 (once server is ready)
python3 src/load_test/load_test.py --concurrency 10 --requests 5
```

Good luck! 🚀

