#!/usr/bin/env python3
"""
Load Testing & Latency Benchmarking for Voice Bot

Simulates multiple concurrent connections and measures key performance metrics:

🎯 KEY METRICS:
  ⚡ Time to First Token (TTFT): Time from speech_end → first audio chunk
     - Measures STT + LLM + TTS pipeline latency
     - Critical for perceived responsiveness
  
  🏁 Total Response Time: Time from speech_end → response fully delivered
     - Measures complete end-to-end latency
     - Includes full agent response generation

📊 Additional Metrics:
  - Connection establishment time
  - Success/failure rates
  - Request type distribution
  - Percentile analysis (P95, P99)

⚠️  IMPORTANT - AUDIO REQUIREMENTS:
  This load test generates synthetic audio that may NOT be processed correctly by Deepgram STT.
  
  For accurate load testing, you have TWO options:
  
  Option 1: Use REAL audio files (RECOMMENDED)
    - Record actual speech samples
    - Save as .wav files
    - Modify generate_test_audio() to load real files
  
  Option 2: Accept STT failures (for connection/infrastructure testing only)
    - Current synthetic audio will likely be rejected by Deepgram
    - Tests connection handling and error paths
    - Will show 0% success rate for actual responses
    - Still useful for testing server stability under load

Test Scenarios:
  1. Simple Query: Basic query-response flow
  2. Tool Call: Queries that trigger async tool execution
  3. Interruption: Real-time interruptions mid-response
  4. False Alarm: Noise detection that should resume playback

Usage:
    # Basic load test with 10 concurrent clients
    python3 load_test.py --concurrency 10 --requests 5
    
    # High concurrency test
    python3 load_test.py --concurrency 50 --requests 10
    
    # Test interruption handling heavily
    python3 load_test.py --concurrency 10 --interruptions 0.5 --false-alarms 0.3 --simple 0.2
    
    # Tool-heavy workload
    python3 load_test.py --concurrency 20 --requests 5 --tools 0.8 --simple 0.2

To generate sample audio files:
    python3 sample_audio.py
"""

import asyncio
import websockets
import json
import time
import statistics
import argparse
from datetime import datetime
from typing import List, Dict, Optional
import random
import base64


class PerformanceMetrics:
    """Track and calculate performance metrics."""
    
    def __init__(self):
        self.connection_times: List[float] = []
        self.time_to_first_token: List[float] = []  # TTFT: speech_end → first audio chunk
        self.total_response_times: List[float] = []  # End-to-end: speech_end → response complete
        
        self.successful_requests = 0
        self.failed_requests = 0
        self.connection_errors = 0
        
        self.request_types: Dict[str, int] = {
            "simple_query": 0,
            "tool_call": 0,
            "interruption": 0,
            "false_alarm": 0,
        }
        
        self.audio_files_used: Dict[str, int] = {}  # Track which audio files were used
    
    def add_connection_time(self, duration: float):
        self.connection_times.append(duration)
    
    def add_ttft(self, duration: float):
        """Add Time to First Token (TTFT) measurement."""
        self.time_to_first_token.append(duration)
    
    def add_total_response_time(self, duration: float):
        """Add total response time (end-to-end) measurement."""
        self.total_response_times.append(duration)
    
    def track_audio_file(self, filename: str):
        """Track which audio file was used."""
        self.audio_files_used[filename] = self.audio_files_used.get(filename, 0) + 1
    
    def record_success(self, request_type: str = "simple_query"):
        self.successful_requests += 1
        self.request_types[request_type] = self.request_types.get(request_type, 0) + 1
    
    def record_failure(self):
        self.failed_requests += 1
    
    def record_connection_error(self):
        self.connection_errors += 1
    
    def get_stats(self, values: List[float]) -> Dict:
        """Calculate statistics for a list of values."""
        if not values:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}
        
        sorted_vals = sorted(values)
        return {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": sorted_vals[int(len(sorted_vals) * 0.95)] if len(sorted_vals) > 0 else 0,
            "p99": sorted_vals[int(len(sorted_vals) * 0.99)] if len(sorted_vals) > 0 else 0,
        }
    
    def print_report(self):
        """Print detailed performance report."""
        print("\n" + "="*80)
        print("🎯 LOAD TEST PERFORMANCE REPORT")
        print("="*80)
        
        # Summary
        total_requests = self.successful_requests + self.failed_requests
        success_rate = (self.successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        print(f"\n📊 SUMMARY")
        print(f"  Total Requests:      {total_requests}")
        print(f"  ✅ Successful:       {self.successful_requests} ({success_rate:.1f}%)")
        print(f"  ❌ Failed:           {self.failed_requests}")
        print(f"  🔌 Connection Errors: {self.connection_errors}")
        
        # Request types breakdown
        if self.request_types:
            print(f"\n📋 REQUEST TYPES")
            for req_type, count in self.request_types.items():
                print(f"  {req_type}: {count}")
        
        # Audio files distribution (shows permutations/combinations used)
        if self.audio_files_used:
            print(f"\n🎵 AUDIO FILES USED (Permutations/Combinations)")
            total_audio_requests = sum(self.audio_files_used.values())
            print(f"  Total unique audio combinations: {len(self.audio_files_used)}")
            print(f"  Distribution:")
            for filename, count in sorted(self.audio_files_used.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_audio_requests * 100) if total_audio_requests > 0 else 0
                print(f"    {filename}: {count} times ({percentage:.1f}%)")
        
        # Connection latency
        if self.connection_times:
            conn_stats = self.get_stats(self.connection_times)
            print(f"\n🔌 CONNECTION LATENCY")
            self._print_stats(conn_stats)
        
        # TIME TO FIRST TOKEN (TTFT) - Key Metric!
        if self.time_to_first_token:
            ttft_stats = self.get_stats(self.time_to_first_token)
            print(f"\n⚡ TIME TO FIRST TOKEN (TTFT)")
            print(f"   📍 Definition: Time from speech_end → first audio chunk received")
            self._print_stats(ttft_stats)
        
        # TOTAL RESPONSE TIME - Key Metric!
        if self.total_response_times:
            total_stats = self.get_stats(self.total_response_times)
            print(f"\n🏁 TOTAL RESPONSE TIME")
            print(f"   📍 Definition: Time from speech_end → response fully delivered")
            self._print_stats(total_stats)
        
        print("\n" + "="*80 + "\n")
    
    def _print_stats(self, stats: Dict):
        """Helper to print statistics in a consistent format."""
        print(f"     Min:    {stats['min']*1000:7.1f}ms  ({stats['min']:.3f}s)")
        print(f"     Mean:   {stats['mean']*1000:7.1f}ms  ({stats['mean']:.3f}s)")
        print(f"     Median: {stats['median']*1000:7.1f}ms  ({stats['median']:.3f}s)")
        print(f"     P95:    {stats['p95']*1000:7.1f}ms  ({stats['p95']:.3f}s)")
        print(f"     P99:    {stats['p99']*1000:7.1f}ms  ({stats['p99']:.3f}s)")
        print(f"     Max:    {stats['max']*1000:7.1f}ms  ({stats['max']:.3f}s)")


class VoiceBotClient:
    """Simulated voice bot client for load testing."""
    
    def __init__(self, client_id: int, server_url: str, metrics: PerformanceMetrics):
        self.client_id = client_id
        self.server_url = server_url
        self.metrics = metrics
        self.ws = None
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        try:
            start_time = time.time()
            self.ws = await websockets.connect(self.server_url)
            duration = time.time() - start_time
            self.metrics.add_connection_time(duration)
            print(f"[Client {self.client_id}] ✓ Connected in {duration:.3f}s")
            return True
        except Exception as e:
            print(f"[Client {self.client_id}] ✗ Connection failed: {e}")
            self.metrics.record_connection_error()
            return False
    
    async def disconnect(self):
        """Close WebSocket connection."""
        if self.ws:
            await self.ws.close()
    
    def generate_test_audio(self, duration_ms: int = 2000) -> str:
        """
        Load real audio file and convert to base64.
        
        Uses pre-recorded speech samples for realistic load testing.
        Falls back to synthetic audio if files are not found.
        """
        import os
        import glob
        
        # Map duration to audio file patterns
        audio_patterns = {
            300: "audio_samples/noise_*.wav",           # False alarm (0.3s)
            1500: "audio_samples/query_1_5s_*.wav",     # Interruption (1.5s)
            2000: "audio_samples/query_2s_*.wav",       # Normal query (2s)
            3000: "audio_samples/query_3s_*.wav",       # Tool call (3s)
        }
        
        # Get pattern for this duration (default to 2s if not found)
        pattern = audio_patterns.get(duration_ms, "audio_samples/query_2s_*.wav")
        audio_dir = os.path.join(os.path.dirname(__file__), pattern)
        
        # Find all matching audio files
        matching_files = glob.glob(audio_dir)
        
        if matching_files:
            # Randomly select one of the matching files
            audio_file = random.choice(matching_files)
            filename = os.path.basename(audio_file)
            
            try:
                with open(audio_file, 'rb') as f:
                    audio_bytes = f.read()
                print(f"[Client {self.client_id}] 🎵 Using audio: {filename}")
                self.metrics.track_audio_file(filename)
                return base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                print(f"[Client {self.client_id}] ⚠️ Error reading audio file: {e}")
        
        # Fallback: Generate synthetic audio (will likely fail with Deepgram)
        print(f"[Client {self.client_id}] ⚠️ No real audio found, using synthetic (expect failures)")
        return self._generate_synthetic_audio(duration_ms)
    
    def _generate_synthetic_audio(self, duration_ms: int = 2000) -> str:
        """Generate synthetic audio as fallback (likely to be rejected by Deepgram)."""
        # Minimal WebM header
        webm_header = bytes([
            0x1A, 0x45, 0xDF, 0xA3,  # EBML Header
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F,
            0x42, 0x86, 0x81, 0x01,
            0x42, 0xF7, 0x81, 0x01,
            0x42, 0xF2, 0x81, 0x04,
            0x42, 0xF3, 0x81, 0x08,
            0x42, 0x82, 0x84, 0x77, 0x65, 0x62, 0x6D,
            0x42, 0x87, 0x81, 0x02,
            0x42, 0x85, 0x81, 0x02,
        ])
        
        bytes_per_second = 8000
        num_bytes = int(bytes_per_second * duration_ms / 1000)
        audio_data = webm_header + bytes([random.randint(0, 255) for _ in range(min(num_bytes, 1000))])
        
        return base64.b64encode(audio_data).decode('utf-8')
    
    async def send_speech_event(self, audio_duration_ms: int = 2000):
        """Simulate speech_start and speech_end events."""
        # Send speech_start
        await self.ws.send(json.dumps({
            "type": "speech_start"
        }))
        
        # Simulate recording duration
        await asyncio.sleep(audio_duration_ms / 1000)
        
        # Send speech_end with audio
        audio_data = self.generate_test_audio(audio_duration_ms)
        await self.ws.send(json.dumps({
            "type": "speech_end",
            "audio": audio_data
        }))
    
    async def wait_for_response(self, timeout: float = 30.0, initial_wait: float = 2.0) -> Dict:
        """
        Wait for server response and track metrics.
        
        Tracks two key metrics:
        1. Time to First Token (TTFT): Time until first audio chunk arrives
        2. Total Response Time: Time until response is fully delivered
        
        Args:
            timeout: Maximum time to wait for complete response
            initial_wait: Minimum time to wait before checking for responses (allows server processing time)
        """
        start_time = time.time()
        first_audio_received = False
        ttft = None  # Time to first token
        audio_chunks_received = 0
        last_audio_time = time.time()
        
        # Wait minimum time to allow server to process STT → LLM → TTS
        await asyncio.sleep(initial_wait)
        
        try:
            while True:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=3.0)
                    data = json.loads(message)
                    event = data.get("event")
                    
                    if event == "play_audio":
                        audio_chunks_received += 1
                        last_audio_time = time.time()
                        
                        if not first_audio_received:
                            # TTFT: Time to receive first audio chunk
                            ttft = time.time() - start_time
                            self.metrics.add_ttft(ttft)
                            first_audio_received = True
                            print(f"[Client {self.client_id}] ⚡ TTFT: {ttft*1000:.1f}ms")
                
                except asyncio.TimeoutError:
                    # No messages for 3s - assume response complete
                    if first_audio_received:
                        break
                    else:
                        print(f"[Client {self.client_id}] ⚠️  No response received (timeout)")
                        raise
            
            # Total Response Time: From start to last audio chunk
            total_time = time.time() - start_time
            self.metrics.add_total_response_time(total_time)
            
            print(f"[Client {self.client_id}] 🏁 Total: {total_time*1000:.1f}ms ({audio_chunks_received} chunks)")
            
            return {
                "success": True,
                "ttft": ttft,
                "total_time": total_time,
                "audio_chunks": audio_chunks_received
            }
        
        except asyncio.TimeoutError:
            print(f"[Client {self.client_id}] ⚠️  Response timeout")
            return {"success": False, "error": "timeout"}
        except Exception as e:
            print(f"[Client {self.client_id}] ✗ Error: {e}")
            return {"success": False, "error": str(e)}
    
    async def run_test_scenario(self, scenario_type: str = "simple_query"):
        """Run a specific test scenario."""
        try:
            if scenario_type == "simple_query":
                await self.send_speech_event(audio_duration_ms=2000)
                result = await self.wait_for_response()
                if result["success"]:
                    self.metrics.record_success("simple_query")
                else:
                    self.metrics.record_failure()
            
            elif scenario_type == "tool_call":
                # Simulate query that triggers tool call
                await self.send_speech_event(audio_duration_ms=3000)
                result = await self.wait_for_response(timeout=45.0)  # Tools take longer
                if result["success"]:
                    self.metrics.record_success("tool_call")
                else:
                    self.metrics.record_failure()
            
            elif scenario_type == "interruption":
                # Realistic interruption: Wait for agent to START responding, then interrupt
                print(f"[Client {self.client_id}] 🎭 Interruption scenario starting...")
                
                # 1. Send initial query
                await self.send_speech_event(audio_duration_ms=2000)
                print(f"[Client {self.client_id}]   → Sent initial query")
                
                # 2. Wait for agent to start responding (receive first audio chunk)
                # Wait at least 2 seconds for server processing
                await asyncio.sleep(2.0)
                
                start_time = time.time()
                first_audio_received = False
                
                try:
                    while not first_audio_received and (time.time() - start_time) < 10.0:
                        message = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                        data = json.loads(message)
                        if data.get("event") == "play_audio":
                            first_audio_received = True
                            print(f"[Client {self.client_id}]   ✓ Agent started responding")
                            break
                except asyncio.TimeoutError:
                    print(f"[Client {self.client_id}]   ⚠️ No response to interrupt")
                
                # 3. NOW interrupt while agent is speaking
                if first_audio_received:
                    # Small delay to simulate user interrupting mid-response
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    
                    print(f"[Client {self.client_id}]   🚨 Interrupting with new query...")
                    await self.send_speech_event(audio_duration_ms=1500)
                    
                    # 4. Wait for the interruption response
                    result = await self.wait_for_response()
                    if result["success"]:
                        self.metrics.record_success("interruption")
                        print(f"[Client {self.client_id}]   ✓ Interruption handled successfully")
                    else:
                        self.metrics.record_failure()
                else:
                    # Couldn't interrupt - no initial response
                    self.metrics.record_failure()
            
            elif scenario_type == "false_alarm":
                # False alarm: Start speaking, then stop (no actual interruption)
                print(f"[Client {self.client_id}] 🎭 False alarm scenario...")
                
                # 1. Send initial query
                await self.send_speech_event(audio_duration_ms=2000)
                
                # 2. Wait for agent to start responding
                # Wait at least 2 seconds for server processing
                await asyncio.sleep(2.0)
                
                start_time = time.time()
                first_audio_received = False
                
                try:
                    while not first_audio_received and (time.time() - start_time) < 10.0:
                        message = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                        data = json.loads(message)
                        if data.get("event") == "play_audio":
                            first_audio_received = True
                            break
                except asyncio.TimeoutError:
                    pass
                
                # 3. Send speech_start (pretend to interrupt)
                if first_audio_received:
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    await self.ws.send(json.dumps({"type": "speech_start"}))
                    print(f"[Client {self.client_id}]   → Sent speech_start (false alarm)")
                    
                    # 4. Immediately send empty audio (false alarm - just noise)
                    await asyncio.sleep(0.3)
                    await self.ws.send(json.dumps({
                        "type": "speech_end",
                        "audio": self.generate_test_audio(300)  # Very short audio = noise
                    }))
                    print(f"[Client {self.client_id}]   → False alarm complete (should resume)")
                    
                    # 5. Wait for playback to resume
                    result = await self.wait_for_response(timeout=15.0)
                    if result["success"]:
                        self.metrics.record_success("false_alarm")
                    else:
                        self.metrics.record_failure()
                else:
                    self.metrics.record_failure()
        
        except Exception as e:
            print(f"[Client {self.client_id}] ✗ Scenario failed: {e}")
            self.metrics.record_failure()


async def run_client_session(
    client_id: int,
    server_url: str,
    metrics: PerformanceMetrics,
    num_requests: int,
    scenario_weights: Dict[str, float]
):
    """Run a complete client session with multiple requests."""
    client = VoiceBotClient(client_id, server_url, metrics)
    
    # Connect
    connected = await client.connect()
    if not connected:
        return
    
    try:
        # Run multiple requests
        for request_num in range(num_requests):
            # Choose scenario based on weights
            scenario = random.choices(
                list(scenario_weights.keys()),
                weights=list(scenario_weights.values())
            )[0]
            
            print(f"[Client {client_id}] Request {request_num + 1}/{num_requests} ({scenario})")
            await client.run_test_scenario(scenario)
            
            # Brief pause between requests
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    finally:
        await client.disconnect()
        print(f"[Client {client_id}] ✓ Session complete")


async def run_load_test(
    server_url: str,
    concurrency: int,
    requests_per_client: int,
    scenario_weights: Dict[str, float]
):
    """Run load test with multiple concurrent clients."""
    metrics = PerformanceMetrics()
    
    print(f"\n🚀 Starting load test:")
    print(f"  Server: {server_url}")
    print(f"  Concurrency: {concurrency}")
    print(f"  Requests per client: {requests_per_client}")
    print(f"  Total requests: {concurrency * requests_per_client}")
    print(f"  Scenarios: {scenario_weights}\n")
    
    start_time = time.time()
    
    # Create concurrent client sessions
    tasks = []
    for client_id in range(concurrency):
        task = asyncio.create_task(
            run_client_session(
                client_id,
                server_url,
                metrics,
                requests_per_client,
                scenario_weights
            )
        )
        tasks.append(task)
    
    # Wait for all clients to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    
    total_duration = time.time() - start_time
    
    # Print results
    print(f"\n✅ Load test complete in {total_duration:.2f}s")
    metrics.print_report()


def main():
    parser = argparse.ArgumentParser(description="Voice Bot Load Testing")
    parser.add_argument(
        "--server",
        default="ws://localhost:8000/ws",
        help="WebSocket server URL (default: ws://localhost:8000/ws)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent connections (default: 10)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=5,
        help="Requests per client (default: 5)"
    )
    parser.add_argument(
        "--simple",
        type=float,
        default=0.6,
        help="Weight for simple queries (default: 0.6)"
    )
    parser.add_argument(
        "--tools",
        type=float,
        default=0.2,
        help="Weight for tool call queries (default: 0.2)"
    )
    parser.add_argument(
        "--interruptions",
        type=float,
        default=0.1,
        help="Weight for interruption scenarios (default: 0.1)"
    )
    parser.add_argument(
        "--false-alarms",
        type=float,
        default=0.1,
        help="Weight for false alarm scenarios (default: 0.1)"
    )
    
    args = parser.parse_args()
    
    # Scenario weights
    scenario_weights = {
        "simple_query": args.simple,
        "tool_call": args.tools,
        "interruption": args.interruptions,
        "false_alarm": args.false_alarms,
    }
    
    # Run load test
    try:
        asyncio.run(run_load_test(
            args.server,
            args.concurrency,
            args.requests,
            scenario_weights
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Load test interrupted by user")


if __name__ == "__main__":
    main()

