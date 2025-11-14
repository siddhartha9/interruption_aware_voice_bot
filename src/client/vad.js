/**
 * Client-Side Voice Activity Detection (VAD)
 * 
 * Detects when user starts and stops speaking using simple energy-based detection.
 * For production, consider using @ricky0123/vad-web or similar library.
 */

class ClientVAD {
  constructor(options = {}) {
    this.aggressiveness = options.aggressiveness || 3;
    this.energyThreshold = options.energyThreshold || 0.01; // RMS threshold
    this.silenceThreshold = options.silenceThreshold || 10; // frames
    this.speechThreshold = options.speechThreshold || 3; // frames
    
    // State
    this.isSpeaking = false;
    this.silenceFrames = 0;
    this.speechFrames = 0;
    
    console.log('[VAD] Initialized with aggressiveness:', this.aggressiveness);
  }
  
  /**
   * Process an audio chunk and detect speech events
   * 
   * @param {Float32Array} audioData - Audio samples normalized between -1 and 1
   * @returns {string} Event: 'START', 'SPEECH', 'END', or 'SILENCE'
   */
  processChunk(audioData) {
    const hasSpeech = this.detectSpeech(audioData);
    
    if (hasSpeech) {
      this.speechFrames++;
      this.silenceFrames = 0;
      
      if (!this.isSpeaking && this.speechFrames >= this.speechThreshold) {
        // Transition: SILENCE -> SPEECH
        this.isSpeaking = true;
        console.log('[VAD] Speech START detected');
        return 'START';
      } else if (this.isSpeaking) {
        return 'SPEECH';
      }
    } else {
      this.silenceFrames++;
      this.speechFrames = 0;
      
      if (this.isSpeaking && this.silenceFrames >= this.silenceThreshold) {
        // Transition: SPEECH -> SILENCE
        this.isSpeaking = false;
        console.log('[VAD] Speech END detected');
        return 'END';
      } else if (this.isSpeaking) {
        // Still in speech, but this chunk is silent
        return 'SPEECH';
      }
    }
    
    return 'SILENCE';
  }
  
  /**
   * Detect speech in audio chunk using RMS energy
   * 
   * @param {Float32Array} audioData - Audio samples
   * @returns {boolean} True if speech detected
   */
  detectSpeech(audioData) {
    if (!audioData || audioData.length === 0) {
      return false;
    }
    
    // Calculate RMS (Root Mean Square) energy
    const rms = this.calculateRMS(audioData);
    
    // Adjust threshold based on aggressiveness
    const threshold = this.energyThreshold * (4 - this.aggressiveness);
    
    return rms > threshold;
  }
  
  /**
   * Calculate RMS energy of audio samples
   * 
   * @param {Float32Array} audioData - Audio samples
   * @returns {number} RMS value
   */
  calculateRMS(audioData) {
    let sum = 0;
    for (let i = 0; i < audioData.length; i++) {
      sum += audioData[i] * audioData[i];
    }
    return Math.sqrt(sum / audioData.length);
  }
  
  /**
   * Reset VAD state
   */
  reset() {
    this.isSpeaking = false;
    this.silenceFrames = 0;
    this.speechFrames = 0;
    console.log('[VAD] State reset');
  }
  
  /**
   * Set energy threshold dynamically
   * 
   * @param {number} threshold - New threshold value
   */
  setThreshold(threshold) {
    this.energyThreshold = threshold;
    console.log('[VAD] Threshold updated to:', threshold);
  }
}

// For production, use a more sophisticated VAD library:
// 
// Option 1: @ricky0123/vad-web (Silero VAD in browser)
// import { MicVAD } from "@ricky0123/vad-web"
// const vad = await MicVAD.new({
//   onSpeechStart: () => console.log("Speech start"),
//   onSpeechEnd: (audio) => console.log("Speech end", audio),
// })
//
// Option 2: WebRTC VAD (if available via WASM)
// Option 3: ML-based VAD using TensorFlow.js

export default ClientVAD;

