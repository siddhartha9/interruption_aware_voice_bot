#!/usr/bin/env python3
"""
Generate sample audio files for load testing.

Creates real audio files that Deepgram can process.
"""

import wave
import struct
import math
import base64


def generate_sine_wave_audio(duration_seconds: float = 2.0, frequency: int = 440) -> bytes:
    """
    Generate a real WAV file with a sine wave tone.
    
    This creates valid audio that Deepgram can actually transcribe
    (though it won't produce meaningful text, it won't error out).
    
    Args:
        duration_seconds: Length of audio in seconds
        frequency: Frequency of sine wave in Hz (440 = A note)
        
    Returns:
        bytes: WAV file data
    """
    sample_rate = 16000  # 16kHz
    num_samples = int(sample_rate * duration_seconds)
    
    # Generate sine wave samples
    samples = []
    for i in range(num_samples):
        sample = math.sin(2 * math.pi * frequency * i / sample_rate)
        # Convert to 16-bit integer
        sample_int = int(sample * 32767)
        samples.append(sample_int)
    
    # Create WAV file in memory
    import io
    wav_buffer = io.BytesIO()
    
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        # Write samples
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))
    
    return wav_buffer.getvalue()


def generate_speech_like_audio(duration_seconds: float = 2.0) -> bytes:
    """
    Generate audio with multiple frequencies to simulate speech.
    
    This is more realistic than a single tone and may produce
    better results with Deepgram (or at least won't error).
    """
    sample_rate = 16000
    num_samples = int(sample_rate * duration_seconds)
    
    # Multiple frequencies to simulate speech formants
    frequencies = [200, 400, 800, 1600]  # Typical speech frequency ranges
    
    samples = []
    for i in range(num_samples):
        # Mix multiple sine waves
        sample = 0.0
        for freq in frequencies:
            sample += 0.25 * math.sin(2 * math.pi * freq * i / sample_rate)
        
        # Add some variation (amplitude modulation)
        envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / sample_rate)
        sample *= envelope
        
        # Convert to 16-bit integer
        sample_int = int(sample * 16384)  # Lower amplitude
        samples.append(sample_int)
    
    # Create WAV file
    import io
    wav_buffer = io.BytesIO()
    
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))
    
    return wav_buffer.getvalue()


def audio_to_base64(audio_bytes: bytes) -> str:
    """Convert audio bytes to base64 string for WebSocket transmission."""
    return base64.b64encode(audio_bytes).decode('utf-8')


if __name__ == "__main__":
    # Generate sample audio files
    print("Generating sample audio files...")
    
    # 2-second speech-like audio
    audio_2s = generate_speech_like_audio(2.0)
    with open("test_audio_2s.wav", "wb") as f:
        f.write(audio_2s)
    print(f"✓ Generated test_audio_2s.wav ({len(audio_2s)} bytes)")
    
    # 3-second for tool calls
    audio_3s = generate_speech_like_audio(3.0)
    with open("test_audio_3s.wav", "wb") as f:
        f.write(audio_3s)
    print(f"✓ Generated test_audio_3s.wav ({len(audio_3s)} bytes)")
    
    # 1.5-second for interruptions
    audio_1_5s = generate_speech_like_audio(1.5)
    with open("test_audio_1_5s.wav", "wb") as f:
        f.write(audio_1_5s)
    print(f"✓ Generated test_audio_1_5s.wav ({len(audio_1_5s)} bytes)")
    
    # 0.3-second for false alarms
    audio_0_3s = generate_speech_like_audio(0.3)
    with open("test_audio_0_3s.wav", "wb") as f:
        f.write(audio_0_3s)
    print(f"✓ Generated test_audio_0_3s.wav ({len(audio_0_3s)} bytes)")
    
    print("\nSample files created! These contain sine waves that Deepgram can process.")
    print("Note: Deepgram may not transcribe meaningful text, but won't error out.")

