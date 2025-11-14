# Voice Bot Load Testing Guide

## 🚨 Current Issue: Synthetic Audio Limitations

### Why Your Load Test is Failing (0% success rate)

The current load test generates **synthetic/fake audio** that Deepgram STT **cannot process**. When Deepgram rejects the audio or returns no transcript, your server doesn't send a response, causing the client to timeout.

```
[Client 0] Request 1/5 (simple_query)
[Client 0] ⚠️  No response received (timeout)
[Client 0] ⚠️  Response timeout
```

## ✅ Solutions

### Option 1: Use Real Audio Files (RECOMMENDED)

This is the most accurate way to load test your voice bot.

#### Step 1: Record Real Audio Samples

```bash
# On Mac, use system audio recorder or:
say "What is my account balance?" -o query1.wav --data-format=LEI16@16000 --channels=1

say "Can you email my bank statement?" -o query2.wav --data-format=LEI16@16000 --channels=1

say "Tell me about my recent transactions" -o query3.wav --data-format=LEI16@16000 --channels=1
```

Or use your browser:
```javascript
// Record in browser console
navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
  const recorder = new MediaRecorder(stream);
  recorder.start();
  // Speak your query
  setTimeout(() => {
    recorder.stop();
    recorder.ondataavailable = e => {
      // Download the blob as a .wav file
      const url = URL.createObjectURL(e.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'query.wav';
      a.click();
    };
  }, 3000);
});
```

#### Step 2: Save Audio Files

```bash
# Create audio directory
mkdir -p src/load_test/audio_samples/

# Move your recorded audio there
mv query*.wav src/load_test/audio_samples/
```

#### Step 3: Modify Load Test to Use Real Audio

Edit `load_test.py`, find the `generate_test_audio()` method and replace it:

```python
def generate_test_audio(self, duration_ms: int = 2000) -> str:
    """Load real audio file and convert to base64."""
    import os
    
    # Map duration to audio file
    audio_files = {
        300: "audio_samples/noise.wav",        # False alarm
        1500: "audio_samples/short_query.wav", # Interruption
        2000: "audio_samples/query_2s.wav",    # Normal query
        3000: "audio_samples/query_3s.wav",    # Tool call query
    }
    
    # Select closest matching file
    audio_file = audio_files.get(duration_ms, "audio_samples/query_2s.wav")
    file_path = os.path.join(os.path.dirname(__file__), audio_file)
    
    try:
        with open(file_path, 'rb') as f:
            audio_bytes = f.read()
        return base64.b64encode(audio_bytes).decode('utf-8')
    except FileNotFoundError:
        print(f"⚠️  Audio file not found: {file_path}")
        print("⚠️  Falling back to synthetic audio (will likely fail)")
        # Fall back to synthetic audio
        return self.generate_synthetic_audio(duration_ms)
```

#### Step 4: Run Load Test

```bash
python3 src/load_test/load_test.py --concurrency 10 --requests 5
```

Now you should see actual responses!

---

### Option 2: Generate Speech-Like Audio (Partial Solution)

Generate audio files with sine waves that Deepgram might accept:

```bash
# Generate sample audio files
cd src/load_test
python3 sample_audio.py

# This creates:
# - test_audio_2s.wav
# - test_audio_3s.wav
# - test_audio_1_5s.wav
# - test_audio_0_3s.wav
```

**Note**: These are sine waves, not speech. Deepgram may:
- Process them but return no transcript (still causes timeout)
- Return "beep" or similar
- Accept but not produce useful results

**Bottom line**: Better than raw zeros, but still not ideal.

---

### Option 3: Test Without STT (Infrastructure/Connection Testing Only)

If you only want to test:
- Connection handling
- WebSocket stability
- Server resource usage
- Error handling paths

Then the current synthetic audio is **fine**. You're testing the failure path, which is also valuable!

**What this tests**:
- ✅ Can server handle 100 concurrent WebSocket connections?
- ✅ Does server crash under load?
- ✅ Are timeouts handled correctly?
- ✅ Connection setup performance
- ❌ NOT testing actual STT → LLM → TTS pipeline

---

## 📊 Expected Results

### With Real Audio (Good Test):
```
📊 SUMMARY
  Total Requests:      50
  ✅ Successful:       48 (96.0%)  ← Good!
  ❌ Failed:           2
  
⚡ TIME TO FIRST TOKEN (TTFT)
     Mean:   1823.5ms  (1.824s)
     P95:    2456.0ms  (2.456s)
```

### With Synthetic Audio (Current State):
```
📊 SUMMARY
  Total Requests:      300
  ✅ Successful:       0 (0.0%)  ← Expected with fake audio
  ❌ Failed:           300
  
⚡ TIME TO FIRST TOKEN (TTFT)
     No data (no responses received)
```

---

## 🎯 Recommended Approach

### For Full End-to-End Testing:
1. Record 5-10 real audio samples (different queries)
2. Modify `generate_test_audio()` to randomly select from real files
3. Run load test with moderate concurrency (10-20)
4. Analyze TTFT and success rates

### For Quick Infrastructure Testing:
1. Use current synthetic audio (it's fine for this purpose)
2. Run high concurrency tests (50-100)
3. Monitor server resource usage
4. Check for crashes or connection errors
5. Don't expect actual responses

### For Development/Debug:
1. Use your actual web client (`client_app/index.html`)
2. Speak real queries
3. Manually test interruptions and false alarms
4. This gives you the most realistic user experience

---

## 🔧 Quick Fix for Testing Right Now

If you want to test the infrastructure immediately without real audio:

```bash
# Test connection handling only (expect failures)
python3 src/load_test/load_test.py --concurrency 10 --requests 3

# Monitor server logs for:
# - Deepgram errors (expected)
# - Server crashes (NOT expected)
# - Memory leaks (NOT expected)
# - Connection errors (NOT expected)
```

If your server:
- ✅ **Stays running**: Good! Infrastructure is solid
- ✅ **Handles 10 concurrent connections**: Good! Scales well
- ✅ **No crashes**: Good! Error handling works
- ❌ **0% success rate**: Expected with fake audio, don't worry!

---

## 💡 Future Enhancement: Test Mode

Consider adding a `--test-mode` flag to your server that:
1. Bypasses Deepgram STT
2. Uses mock transcripts
3. Responds with canned responses
4. Allows load testing without hitting API quotas

```python
# Example server modification
if os.getenv("TEST_MODE") == "true":
    # Mock STT response
    return "This is a test query"
else:
    # Real Deepgram call
    return await deepgram.transcribe(audio)
```

This would enable true load testing without real audio or API costs!

---

## 📚 Summary

| Goal | Solution | Success Rate |
|------|----------|--------------|
| **Full pipeline testing** | Use real audio files | 90-99% |
| **Speech synthesis testing** | Use `sample_audio.py` | 30-70% (may work) |
| **Infrastructure testing** | Use synthetic audio (current) | 0% (expected) |
| **Development testing** | Use web client manually | 100% (with real mic) |

**Bottom line**: For meaningful load test results, **use real audio samples**. 🎤

