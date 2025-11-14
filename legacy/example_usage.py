"""
Example usage of the refactored voice bot orchestrator.

This demonstrates how to use the modular components in a WebSocket application.
"""

import asyncio
from orchestrator import ConnectionOrchestrator


# Mock WebSocket class for demonstration
class MockWebSocket:
    """Mock WebSocket for testing without a real connection."""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_json(self, data):
        """Simulate sending JSON over WebSocket."""
        print(f"[WebSocket] Sending: {data}")
        self.sent_messages.append(data)


async def example_conversation():
    """
    Example conversation flow demonstrating the orchestrator.
    """
    print("=" * 60)
    print("Voice Bot - Example Conversation")
    print("=" * 60)
    
    # 1. Create mock WebSocket
    websocket = MockWebSocket()
    
    # 2. Initialize orchestrator
    orchestrator = ConnectionOrchestrator(websocket)
    
    # 3. Start background workers
    await orchestrator.start_workers()
    
    print("\n[Example] Orchestrator initialized and workers started")
    print("[Example] Simulating a conversation...\n")
    
    try:
        # Simulate conversation flow
        
        # --- Turn 1: User speaks ---
        print("\n" + "="*60)
        print("TURN 1: User asks a question")
        print("="*60)
        
        # Simulate audio chunks arriving (in reality, these come from microphone)
        fake_audio_chunk = b'\x00\x01' * 8000  # Fake 1 second of audio
        
        # Process multiple audio chunks (simulating streaming)
        for i in range(5):
            await orchestrator.process_audio_chunk(fake_audio_chunk)
            await asyncio.sleep(0.05)
        
        # Wait for STT and LLM processing
        await asyncio.sleep(0.5)
        
        print(f"\n[Example] Chat History: {orchestrator.chat_history}")
        
        # --- Turn 2: User interrupts agent ---
        print("\n" + "="*60)
        print("TURN 2: User interrupts during agent response")
        print("="*60)
        
        # Simulate agent is currently speaking (set playback to ACTIVE)
        orchestrator.playback_status = orchestrator.playback_worker.set_active()
        
        # User starts speaking (interruption!)
        await orchestrator.process_audio_chunk(fake_audio_chunk)
        await asyncio.sleep(0.1)
        
        # User finishes their interruption
        for i in range(3):
            await orchestrator.process_audio_chunk(fake_audio_chunk)
            await asyncio.sleep(0.05)
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        print(f"\n[Example] Chat History after interruption: {orchestrator.chat_history}")
        
        # --- Turn 3: False alarm (backchannel) ---
        print("\n" + "="*60)
        print("TURN 3: User says 'uh huh' (false alarm)")
        print("="*60)
        
        # Simulate agent speaking again
        orchestrator.playback_status = orchestrator.playback_worker.set_active()
        
        # User says "uh huh" (should be detected as false alarm)
        await orchestrator.process_audio_chunk(fake_audio_chunk)
        await asyncio.sleep(0.1)
        
        # This should trigger resume, not regenerate
        await asyncio.sleep(0.5)
        
        print(f"\n[Example] Playback should have resumed after false alarm")
        print(f"[Example] Playback Status: {orchestrator.playback_status}")
        
        # Let the system finish processing
        await asyncio.sleep(1.0)
        
    finally:
        # 4. Cleanup
        print("\n" + "="*60)
        print("Cleaning up...")
        print("="*60)
        await orchestrator.cleanup()
        print("[Example] Cleanup complete")
    
    print("\n" + "="*60)
    print("Example conversation complete!")
    print("="*60)
    print(f"\nFinal Chat History ({len(orchestrator.chat_history)} messages):")
    for i, msg in enumerate(orchestrator.chat_history):
        print(f"  {i+1}. [{msg['role']}]: {msg['content'][:50]}...")


async def example_module_testing():
    """
    Example of testing individual modules in isolation.
    """
    print("\n" + "="*60)
    print("Testing Individual Modules")
    print("="*60)
    
    # Test VAD
    from vad import VADProcessor, VADEvent
    print("\n--- Testing VAD ---")
    vad = VADProcessor(aggressiveness=3)
    fake_audio = b'\x00\x01' * 100
    event = vad.process_chunk(fake_audio)
    print(f"VAD Event: {event}")
    
    # Test STT
    from stt import STTProcessor
    print("\n--- Testing STT ---")
    stt = STTProcessor()
    text = await stt.transcribe_audio(fake_audio)
    print(f"STT Result: {text}")
    
    # Test AI Agent
    from ai_agent import AIAgent
    print("\n--- Testing AI Agent ---")
    agent = AIAgent()
    chat_history = [{"role": "user", "content": "Hello!"}]
    async for chunk in agent.generate_response(chat_history):
        if chunk:
            print(f"Agent chunk: {chunk}")
        else:
            print("Agent stream ended")
            break
    
    # Test TTS
    from tts import text_to_speech_base64
    print("\n--- Testing TTS ---")
    audio_b64 = await text_to_speech_base64("Hello world")
    print(f"TTS Result: {len(audio_b64) if audio_b64 else 0} base64 chars")
    
    # Test Interruption Handler
    from interruption_handler import InterruptionHandler
    from state_types import Status, InterruptionStatus
    print("\n--- Testing Interruption Handler ---")
    handler = InterruptionHandler()
    
    # Test false alarm detection
    stt_output = ["uh huh"]
    is_real, text, _ = await handler.decide_action(
        stt_output_list=stt_output,
        chat_history=[],
        playback_status=Status.PAUSED
    )
    print(f"Is 'uh huh' a real interruption? {is_real}")
    
    # Test real interruption
    stt_output = ["Wait, I meant something else"]
    is_real, text, _ = await handler.decide_action(
        stt_output_list=stt_output,
        chat_history=[],
        playback_status=Status.PAUSED
    )
    print(f"Is '{text}' a real interruption? {is_real}")
    
    print("\n" + "="*60)
    print("Module testing complete!")
    print("="*60)


async def main():
    """Main entry point for examples."""
    print("\n🎙️  Voice Bot - Modular Architecture Demo\n")
    
    # Run module testing first
    await example_module_testing()
    
    # Then run full conversation example
    await example_conversation()
    
    print("\n✅ All examples completed successfully!\n")


if __name__ == "__main__":
    asyncio.run(main())

