"""
Prompt Generator Module.

This module handles intelligent prompt construction and modification
based on conversation context and interruption status.
"""

from typing import List, Dict, Optional, Tuple


class PromptGenerator:
    """
    Generates and modifies prompts intelligently based on conversation context.
    
    Responsibilities:
    - Merge multiple STT outputs into coherent prompt
    - Detect false alarms (backchannels like "uh-huh")
    - Construct appropriate prompt based on interruption context
    - Decide whether new prompt generation is needed
    """
    
    def __init__(self):
        """Initialize the prompt generator."""
        # False alarm phrases (backchannels)
        self.false_alarm_phrases = [
            "uh huh",
            "uh-huh",
            "mhmm",
            "mm-hmm",
            "okay",
            "ok",
            "yeah",
            "yep",
            "yes",
            "got it",
            "i see",
            "right",
            "sure",
            "alright",
            "continue",
            "go on",
            "go ahead",
        ]
        
        print("[Prompt Generator] Initialized")
    
    def generate_prompt(
        self,
        stt_output_list: List[str],
        chat_history: List[Dict[str, str]],
        is_interruption: bool
    ) -> Tuple[bool, str, List[Dict[str, str]]]:
        """
        Generate an appropriate prompt based on context and clean up chat history if needed.
        
        This function:
        1. ALWAYS merges all STT outputs into a single coherent prompt
        2. If interrupted, removes the unheard agent response from chat history
        3. Returns the cleaned chat history along with the prompt
        
        Args:
            stt_output_list: List of ALL transcribed text from STT (will be merged)
            chat_history: Current conversation history (will be modified if interruption)
            is_interruption: Whether this is an interruption or new turn
            
        Returns:
            Tuple of (is_new_prompt_needed, modified_prompt, cleaned_chat_history)
            - is_new_prompt_needed: False for false alarms, True otherwise
            - modified_prompt: The merged and possibly contextualized user input
            - cleaned_chat_history: Chat history with unheard agent responses removed
        """
        # 1. ALWAYS merge ALL STT outputs into single coherent text
        # Example: ["Hello", "I want to", "book a flight"] → "Hello I want to book a flight"
        all_new_text = self._merge_stt_outputs(stt_output_list)
        if not all_new_text.strip():
            print("[Prompt Generator] Empty text, no prompt needed")
            return False, "", chat_history
        
        # 2. If not an interruption, this is a new turn
        if not is_interruption:
            print(f"[Prompt Generator] New turn: '{all_new_text}'")
            return True, all_new_text, chat_history
        
        # 3. If interruption, check if it's a false alarm
        is_false_alarm = self._is_false_alarm(all_new_text)
        
        if is_false_alarm:
            print(f"[Prompt Generator] FALSE ALARM detected: '{all_new_text}'")
            return False, all_new_text, chat_history
        
        # 4. Real interruption - clean chat history and append new text
        print(f"[Prompt Generator] REAL INTERRUPTION: '{all_new_text}'")
        
        # Remove the unheard agent response and append new text to previous user message
        cleaned_history = self._clean_chat_history_on_interruption(chat_history, all_new_text)
        
        # The new text is already appended to the last user message in cleaned_history
        # So we return the merged text as the prompt (for logging purposes)
        # But the actual prompt sent to LLM will be the entire cleaned_history
        modified_prompt = all_new_text
        
        return True, modified_prompt, cleaned_history
    
    def _merge_stt_outputs(self, stt_output_list: List[str]) -> str:
        """
        Merge multiple STT outputs intelligently.
        
        Args:
            stt_output_list: List of text snippets from STT
            
        Returns:
            Merged text
        """
        if not stt_output_list:
            return ""
        
        # Simple merge: join with spaces and clean up
        merged = " ".join(stt_output_list)
        
        # Clean up multiple spaces
        merged = " ".join(merged.split())
        
        return merged.strip()
    
    def _is_false_alarm(self, text: str) -> bool:
        """
        Determine if the interruption is a false alarm (backchannel).
        
        False alarms are brief acknowledgments like "uh-huh", "okay", etc.
        
        Args:
            text: Transcribed user text
            
        Returns:
            True if it's a false alarm, False if real interruption
        """
        text_lower = text.lower().strip()
        
        # Check exact match
        if text_lower in self.false_alarm_phrases:
            return True
        
        # Check if text is very short and contains a false alarm phrase
        words = text_lower.split()
        if len(words) <= 2:
            for phrase in self.false_alarm_phrases:
                if phrase in text_lower:
                    return True
        
        # Otherwise, it's a real interruption
        return False
    
    def _clean_chat_history_on_interruption(
        self,
        chat_history: List[Dict[str, str]],
        new_user_text: str
    ) -> List[Dict[str, str]]:
        """
        Clean chat history during interruption and append new text to last user message.
        
        When user interrupts:
        1. Remove the unheard agent response
        2. Append the new user text to the previous user question
        
        This creates a natural flow like:
        - Original: "How are you doing?"
        - New: "What are you doing by the way?"
        - Combined: "How are you doing? What are you doing by the way?"
        
        Args:
            chat_history: Current conversation history
            new_user_text: New text from user interruption
            
        Returns:
            Cleaned chat history with unheard agent response removed and text appended
        """
        if len(chat_history) == 0:
            return chat_history
        
        # Check if last message is from agent
        if chat_history[-1].get("role") == "agent":
            # Remove the unheard agent response
            removed_msg = chat_history[-1]
            cleaned_history = chat_history[:-1].copy()  # Create new list without last item
            print(f"[Prompt Generator] ⚠️ Removed unheard agent response: '{removed_msg['content'][:80]}...'")
            
            # Now append new user text to the previous user message
            if len(cleaned_history) > 0 and cleaned_history[-1].get("role") == "user":
                previous_user_msg = cleaned_history[-1]["content"]
                combined_msg = f"{previous_user_msg} {new_user_text}"
                cleaned_history[-1]["content"] = combined_msg
                print(f"[Prompt Generator] ✓ Appended new text to previous user message")
                print(f"[Prompt Generator]   Combined: '{combined_msg[:100]}...'")
            
            return cleaned_history
        
        # No agent response to remove
        return chat_history
    
    def _construct_interruption_prompt(
        self,
        new_text: str,
        chat_history: List[Dict[str, str]]
    ) -> str:
        """
        Construct an appropriate prompt for an interruption.
        
        Args:
            new_text: New text from the user (all STT outputs merged)
            chat_history: Current conversation history (already cleaned)
            
        Returns:
            Constructed prompt
        """
        # Get the last user message if available
        last_user_message = None
        for msg in reversed(chat_history):
            if msg["role"] == "user":
                last_user_message = msg["content"]
                break
        
        # If we have context, we could construct a more sophisticated prompt
        # For now, just return the new text (all STT outputs already merged)
        # In the future, could do things like:
        # - "Actually, [new_text]" if it seems like a correction
        # - Merge with previous context if it's a continuation
        
        return new_text
    
    def add_false_alarm_phrase(self, phrase: str):
        """
        Add a custom false alarm phrase.
        
        Args:
            phrase: Phrase to add (will be lowercased)
        """
        phrase_lower = phrase.lower().strip()
        if phrase_lower not in self.false_alarm_phrases:
            self.false_alarm_phrases.append(phrase_lower)
            print(f"[Prompt Generator] Added false alarm phrase: '{phrase}'")
    
    def remove_false_alarm_phrase(self, phrase: str):
        """
        Remove a false alarm phrase.
        
        Args:
            phrase: Phrase to remove
        """
        phrase_lower = phrase.lower().strip()
        if phrase_lower in self.false_alarm_phrases:
            self.false_alarm_phrases.remove(phrase_lower)
            print(f"[Prompt Generator] Removed false alarm phrase: '{phrase}'")
    
    def get_false_alarm_phrases(self) -> List[str]:
        """
        Get list of current false alarm phrases.
        
        Returns:
            List of false alarm phrases
        """
        return self.false_alarm_phrases.copy()

