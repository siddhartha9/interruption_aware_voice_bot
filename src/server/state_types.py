"""
State type definitions for the conversation orchestrator.
"""

from enum import Enum


class Status(Enum):
    """Status enum for various system components."""
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    STREAMING = "STREAMING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"


class InterruptionStatus(Enum):
    """Status enum for interruption handling."""
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"  # The "lock" state
    ACTIVE = "ACTIVE"  # The "flag" state

