"""
Speech-to-Text (STT) Module using Deepgram API.

This module transcribes audio into text using Deepgram's Nova-2 model.
"""

import asyncio
import os
from typing import Optional
from deepgram import DeepgramClient


class STTProcessor:
    """
    Speech-to-Text processor using Deepgram Nova-2.
    
    This is a stateless processor that converts audio buffers into text
    using Deepgram's industry-leading transcription API.
    """
    
    def __init__(self, api_key: str, model: str = "nova-2", language: str = "en"):
        """
        Initialize the STT processor with Deepgram.
        
        Args:
            api_key: Deepgram API key
            model: Deepgram model (default: "nova-2" - best quality)
            language: Language code (e.g., "en", "es", "fr")
        """
        self.api_key = api_key
        self.model = model
        self.language = language
        
        # Initialize Deepgram client
        try:
            self.client = DeepgramClient(api_key=api_key)
            print(f"[STT] ✓ Initialized Deepgram with model={model}, language={language}")
        except Exception as e:
            print(f"[STT] ✗ Failed to initialize Deepgram client: {e}")
            raise
    
    async def transcribe_audio(self, audio_buffer: bytes) -> Optional[str]:
        """
        Transcribe an audio buffer into text using Deepgram.
        
        Args:
            audio_buffer: Raw audio bytes (WebM/WAV from browser)
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        if not audio_buffer or len(audio_buffer) == 0:
            print("[STT] Empty audio buffer")
            return None
        
        # Skip very small audio buffers (likely noise or incomplete recordings)
        # WebM files need at least ~5KB to be valid, WAV needs at least ~1KB
        if len(audio_buffer) < 5000:
            print(f"[STT] ⚠️ Audio too small ({len(audio_buffer)} bytes), skipping (likely noise/incomplete)")
            return None
        
        try:
            print(f"[STT] Transcribing {len(audio_buffer)} bytes...")
            
            # Call Deepgram API
            text = await self._call_deepgram_api(audio_buffer)
            
            if text:
                print(f"[STT] ✓ Result: '{text}'")
            else:
                print("[STT] No speech detected in audio")
            
            return text
            
        except Exception as e:
            print(f"[STT] ✗ Error during transcription: {e}")
            # If it's a Deepgram error, log more details
            if "Bad Request" in str(e) or "corrupt" in str(e).lower() or "unsupported" in str(e).lower():
                print(f"[STT] ⚠️ Audio format issue detected. Attempting to handle gracefully...")
            return None
    
    def _detect_audio_format(self, audio_buffer: bytes) -> str:
        """
        Detect audio format from magic bytes.
        
        Args:
            audio_buffer: Raw audio bytes
            
        Returns:
            Encoding string for Deepgram (e.g., "webm", "wav", "mp3")
        """
        if not audio_buffer or len(audio_buffer) < 4:
            # Default to webm if we can't detect
            return "webm"
        
        # Check magic bytes
        # WebM: 1A 45 DF A3 (EBML header)
        if audio_buffer[:4] == b'\x1a\x45\xdf\xa3':
            return "webm"
        
        # WAV: 52 49 46 46 (RIFF)
        if audio_buffer[:4] == b'RIFF':
            return "wav"
        
        # MP3: FF FB or FF F3 (ID3 or frame sync)
        if audio_buffer[:2] == b'\xff\xfb' or audio_buffer[:2] == b'\xff\xf3':
            return "mp3"
        
        # OGG: 4F 67 67 53 (OggS)
        if audio_buffer[:4] == b'OggS':
            return "ogg"
        
        # FLAC: 66 4C 61 43 (fLaC)
        if audio_buffer[:4] == b'fLaC':
            return "flac"
        
        # Default to webm (most common for browser recordings)
        print(f"[STT] ⚠️ Could not detect audio format from magic bytes, defaulting to webm")
        return "webm"
    
    async def _call_deepgram_api(self, audio_buffer: bytes) -> Optional[str]:
        """
        Internal method to call Deepgram API.
        
        Args:
            audio_buffer: Raw audio bytes (WebM/Opus from browser)
            
        Returns:
            Transcribed text or None
        """
        try:
            # Detect audio format for logging
            detected_format = self._detect_audio_format(audio_buffer)
            print(f"[STT] Detected audio format: {detected_format}")
            
            # Deepgram's transcribe_file API can auto-detect format from the audio data
            # We don't specify encoding parameter - let Deepgram auto-detect
            # This works better than specifying encoding, as Deepgram handles WebM/Opus automatically
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.listen.v1.media.transcribe_file(
                    request=audio_buffer,
                    model=self.model,
                    language=self.language,
                    smart_format=True,
                    punctuate=True
                    # Note: Not specifying encoding - Deepgram auto-detects from audio data
                    # This works better for WebM/Opus from browsers
                )
            )
            
            # Debug: Print response structure
            print(f"[STT] Deepgram response type: {type(response)}")
            print(f"[STT] Has 'results': {hasattr(response, 'results')}")
            
            # Extract transcript
            if response and hasattr(response, 'results'):
                channels = response.results.channels
                print(f"[STT] Channels count: {len(channels) if channels else 0}")
                
                if channels and len(channels) > 0:
                    alternatives = channels[0].alternatives
                    print(f"[STT] Alternatives count: {len(alternatives) if alternatives else 0}")
                    
                    if alternatives and len(alternatives) > 0:
                        transcript = alternatives[0].transcript
                        confidence = alternatives[0].confidence if hasattr(alternatives[0], 'confidence') else 'N/A'
                        print(f"[STT] Raw transcript: '{transcript}' (confidence: {confidence})")
                        
                        if transcript and transcript.strip():
                            return transcript.strip()
            
            # No transcript found
            print("[STT] No transcript extracted from response")
            return None
            
        except Exception as e:
            print(f"[STT] Deepgram API error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def set_language(self, language: str):
        """
        Change the transcription language.
        
        Args:
            language: Language code (e.g., "en", "es", "fr")
        """
        self.language = language
        print(f"[STT] Language set to {language}")

