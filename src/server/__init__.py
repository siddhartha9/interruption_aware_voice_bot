"""
Server-side modules for Voice Bot.

This package contains all server-side components:
- ConnectionOrchestrator: Main orchestrator
- STTProcessor: Speech-to-Text
- AIAgent: AI/LLM integration
- TTSProcessor: Text-to-Speech
- InterruptionHandler: Interruption logic
- AudioPlaybackWorker: Audio queue management
- State types and enums
"""

from .orchestrator import ConnectionOrchestrator
from .state_types import Status, InterruptionStatus
from .stt import STTProcessor
from .ai_agent import AIAgent
from .tts import TTSProcessor, TTSError, text_to_speech_base64
from .audio_playback import AudioPlaybackWorker, AudioOutputQueue
from .interruption_handler import InterruptionHandler
from .prompt_generator import PromptGenerator

__all__ = [
    'ConnectionOrchestrator',
    'Status',
    'InterruptionStatus',
    'STTProcessor',
    'AIAgent',
    'TTSProcessor',
    'TTSError',
    'text_to_speech_base64',
    'AudioPlaybackWorker',
    'AudioOutputQueue',
    'InterruptionHandler',
    'PromptGenerator',
]

