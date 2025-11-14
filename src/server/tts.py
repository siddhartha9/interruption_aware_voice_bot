"""
Text-to-Speech (TTS) Module.

This module converts text into audio.
"""

import asyncio
import base64
from typing import Optional


class TTSError(Exception):
    """Exception raised for TTS errors."""
    pass


class TTSProcessor:
    """
    Text-to-Speech processor.
    
    This is a stateless processor that converts text into audio.
    """
    
    def __init__(self, voice: str = "default", speed: float = 1.0):
        """
        Initialize the TTS processor.
        
        Args:
            voice: Voice identifier (depends on TTS provider)
            speed: Speech speed multiplier (0.5-2.0)
        """
        self.voice = voice
        self.speed = speed
        print(f"[TTS] Initialized with voice={voice}, speed={speed}")
    
    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech audio.
        
        Args:
            text: Text to synthesize
            
        Returns:
            Audio bytes (WAV, MP3, or raw PCM), or None if synthesis failed
        """
        if not text or not text.strip():
            return None
        
        try:
            # TODO: Replace this stub with actual TTS implementation
            # Options:
            #   - OpenAI TTS
            #   - ElevenLabs
            #   - Google Cloud Text-to-Speech
            #   - Azure Speech Services
            #   - AWS Polly
            #   - Coqui TTS (local)
            #   - edge-tts (free Microsoft voices)
            
            print(f"[TTS] Synthesizing: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # Stub: Simulate API call
            await asyncio.sleep(0.05)
            
            # Stub: Return fake audio bytes
            audio_bytes = await self._call_tts_api(text)
            
            if audio_bytes:
                print(f"[TTS] Generated {len(audio_bytes)} bytes of audio")
            
            return audio_bytes
            
        except Exception as e:
            raise TTSError(f"TTS synthesis failed: {e}")
    
    async def _call_tts_api(self, text: str) -> Optional[bytes]:
        """
        Internal method to call the actual TTS API.
        
        Args:
            text: Text to synthesize
            
        Returns:
            Audio bytes (MP3 format - widely supported) or None
        """
        try:
            import time
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            start_time = time.time()
            
            # Using gTTS (Google Text-to-Speech) - Free!
            from gtts import gTTS
            from io import BytesIO
            
            print(f"[TTS] ⏱️  Calling gTTS API (non-blocking)...")
            
            # Run blocking gTTS call in thread pool to avoid blocking event loop
            def _sync_tts_call():
                tts = gTTS(text=text, lang='en', slow=False)
                mp3_buffer = BytesIO()
                tts.write_to_fp(mp3_buffer)
                mp3_buffer.seek(0)
                return mp3_buffer.read()
            
            # Run in executor (thread pool)
            loop = asyncio.get_event_loop()
            mp3_data = await loop.run_in_executor(None, _sync_tts_call)
            
            elapsed = time.time() - start_time
            print(f"[TTS] ✅ Generated MP3 audio ({len(mp3_data)} bytes) in {elapsed:.2f}s")
            return mp3_data
            
        except ImportError:
            print("[TTS] WARNING: gTTS not installed. Install with: pip install gTTS")
            print("[TTS] Using simple beep audio as fallback...")
            return self._generate_beep_audio()
            
        except Exception as e:
            print(f"[TTS] Error generating audio: {e}")
            return None
    
    def _generate_beep_audio(self) -> bytes:
        """
        Generate a simple beep audio as fallback.
        Returns a minimal WAV file.
        """
        import struct
        import math
        
        # WAV file parameters
        sample_rate = 16000
        duration = 0.3  # seconds
        frequency = 440  # Hz (A4 note)
        num_samples = int(sample_rate * duration)
        
        # Generate sine wave
        samples = []
        for i in range(num_samples):
            sample = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / sample_rate))
            samples.append(struct.pack('<h', sample))
        
        audio_data = b''.join(samples)
        
        # Create WAV header
        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + len(audio_data),
            b'WAVE',
            b'fmt ',
            16,  # PCM format chunk size
            1,   # PCM format
            1,   # Mono
            sample_rate,
            sample_rate * 2,  # Byte rate
            2,   # Block align
            16,  # Bits per sample
            b'data',
            len(audio_data)
        )
        
        return wav_header + audio_data
    
    def set_voice(self, voice: str):
        """
        Change the TTS voice.
        
        Args:
            voice: Voice identifier
        """
        self.voice = voice
        print(f"[TTS] Voice set to {voice}")
    
    def set_speed(self, speed: float):
        """
        Change the speech speed.
        
        Args:
            speed: Speech speed multiplier (0.5-2.0)
        """
        self.speed = max(0.5, min(2.0, speed))
        print(f"[TTS] Speed set to {self.speed}")


async def text_to_speech_base64(text: str) -> Optional[str]:
    """
    Convenience function to convert text to base64-encoded audio.
    
    This is useful for sending audio over WebSocket connections.
    
    Args:
        text: Text to synthesize
        
    Returns:
        Base64-encoded audio string, or None if synthesis failed
    """
    try:
        # Use a global TTS processor instance or create a new one
        tts = TTSProcessor()
        audio_bytes = await tts.synthesize(text)
        
        if audio_bytes:
            # Encode to base64 for transmission
            b64_string = base64.b64encode(audio_bytes).decode('utf-8')
            return b64_string
        
        return None
        
    except TTSError as e:
        print(f"[TTS] Base64 conversion failed: {e}")
        raise

