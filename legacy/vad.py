"""
Voice Activity Detection (VAD) Module.

This module detects when a user starts and stops speaking.
"""

from enum import Enum


class VADEvent(Enum):
    """Events emitted by the VAD processor."""
    SILENCE = "SILENCE"
    START = "START"  # User starts speaking
    SPEECH = "SPEECH"  # User is speaking (continuation)
    END = "END"  # User stops speaking


class VADProcessor:
    """
    Voice Activity Detection processor.
    
    This is a stateful processor that analyzes incoming audio chunks
    and emits events when speech starts and ends.
    """
    
    def __init__(self, aggressiveness: int = 3):
        """
        Initialize the VAD processor.
        
        Args:
            aggressiveness: VAD sensitivity (0-3, where 3 is most aggressive)
        """
        self.aggressiveness = aggressiveness
        self.is_speaking = False
        self.silence_frames = 0
        self.speech_frames = 0
        
        # Thresholds for triggering events
        self.speech_threshold = 3  # Frames of speech to trigger START
        self.silence_threshold = 10  # Frames of silence to trigger END
        
        print(f"[VAD] Initialized with aggressiveness={aggressiveness}")
    
    def process_chunk(self, audio_chunk: bytes) -> VADEvent:
        """
        Process a single audio chunk and return the current VAD event.
        
        Args:
            audio_chunk: Raw audio bytes (PCM 16-bit, 16kHz recommended)
            
        Returns:
            VADEvent indicating the current speech state
        """
        # TODO: Replace this stub with actual VAD logic
        # Options:
        #   - webrtcvad library
        #   - silero-vad model
        #   - pyannote.audio
        #   - Custom energy-based detection
        
        # Stub implementation: detect speech based on audio energy
        has_speech = self._detect_speech_in_chunk(audio_chunk)
        
        if has_speech:
            self.speech_frames += 1
            self.silence_frames = 0
            
            if not self.is_speaking and self.speech_frames >= self.speech_threshold:
                # Transition: SILENCE -> SPEECH
                self.is_speaking = True
                print("[VAD] Speech START detected")
                return VADEvent.START
            elif self.is_speaking:
                return VADEvent.SPEECH
        else:
            self.silence_frames += 1
            self.speech_frames = 0
            
            if self.is_speaking and self.silence_frames >= self.silence_threshold:
                # Transition: SPEECH -> SILENCE
                self.is_speaking = False
                print("[VAD] Speech END detected")
                return VADEvent.END
            elif self.is_speaking:
                # Still in speech, but this chunk is silent
                return VADEvent.SPEECH
        
        return VADEvent.SILENCE
    
    def _detect_speech_in_chunk(self, audio_chunk: bytes) -> bool:
        """
        Simple energy-based speech detection (stub).
        
        Args:
            audio_chunk: Raw audio bytes
            
        Returns:
            True if speech is detected, False otherwise
        """
        # TODO: Implement proper VAD algorithm
        # For now, use simple energy threshold
        if len(audio_chunk) == 0:
            return False
        
        # Calculate RMS energy
        import struct
        samples = struct.unpack(f"{len(audio_chunk)//2}h", audio_chunk)
        rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
        
        # Threshold (adjust based on your audio characteristics)
        threshold = 500
        return rms > threshold
    
    def reset(self):
        """Reset the VAD state."""
        self.is_speaking = False
        self.silence_frames = 0
        self.speech_frames = 0
        print("[VAD] State reset")

