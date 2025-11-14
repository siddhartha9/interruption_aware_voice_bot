/**
 * Client-Side Audio Player
 * 
 * Manages audio playback with pause/resume capabilities for interruption handling.
 */

class AudioPlayer {
  constructor(options = {}) {
    this.sampleRate = options.sampleRate || 24000;
    
    // Audio context
    this.audioContext = null;
    
    // Playback queue
    this.audioQueue = [];
    this.isPlaying = false;
    this.isPaused = false;
    
    // Current playback
    this.currentSource = null;
    this.pausedAt = 0;
    this.startedAt = 0;
    
    console.log('[AudioPlayer] Initialized');
  }
  
  /**
   * Initialize audio context (must be called after user interaction)
   */
  async initialize() {
    if (this.audioContext) return;
    
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: this.sampleRate
    });
    
    // Resume context if suspended (required by some browsers)
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
    }
    
    console.log('[AudioPlayer] Audio context initialized');
  }
  
  /**
   * Play audio from base64 encoded data
   * 
   * @param {string} base64Audio - Base64 encoded audio
   */
  async play(base64Audio) {
    await this.initialize();
    
    try {
      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      // Decode audio data
      const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
      
      // Add to queue
      this.audioQueue.push(audioBuffer);
      
      // Start playback if not already playing
      if (!this.isPlaying && !this.isPaused) {
        this.playNext();
      }
      
    } catch (error) {
      console.error('[AudioPlayer] Failed to play audio:', error);
    }
  }
  
  /**
   * Play next audio buffer from queue
   */
  async playNext() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      return;
    }
    
    if (this.isPaused) {
      return; // Don't play while paused
    }
    
    this.isPlaying = true;
    const audioBuffer = this.audioQueue.shift();
    
    // Create source node
    this.currentSource = this.audioContext.createBufferSource();
    this.currentSource.buffer = audioBuffer;
    this.currentSource.connect(this.audioContext.destination);
    
    // Track timing
    this.startedAt = this.audioContext.currentTime;
    this.pausedAt = 0;
    
    // Play next when this finishes
    this.currentSource.onended = () => {
      this.currentSource = null;
      this.playNext();
    };
    
    // Start playback
    this.currentSource.start(0);
    console.log('[AudioPlayer] Playing audio chunk');
  }
  
  /**
   * Pause current playback
   */
  pause() {
    if (!this.isPlaying || this.isPaused) return;
    
    this.isPaused = true;
    
    if (this.currentSource) {
      // Stop current playback
      this.pausedAt = this.audioContext.currentTime - this.startedAt;
      this.currentSource.stop();
      this.currentSource = null;
    }
    
    console.log('[AudioPlayer] Playback PAUSED');
  }
  
  /**
   * Resume playback
   */
  resume() {
    if (!this.isPaused) return;
    
    this.isPaused = false;
    console.log('[AudioPlayer] Playback RESUMED');
    
    // Continue with next item in queue
    if (!this.isPlaying) {
      this.playNext();
    }
  }
  
  /**
   * Stop playback and clear queue
   */
  stop() {
    this.isPaused = false;
    this.isPlaying = false;
    
    if (this.currentSource) {
      this.currentSource.stop();
      this.currentSource = null;
    }
    
    this.audioQueue = [];
    console.log('[AudioPlayer] Playback STOPPED');
  }
  
  /**
   * Clear the audio queue (for interruptions)
   */
  clearQueue() {
    this.audioQueue = [];
    console.log('[AudioPlayer] Queue cleared');
  }
  
  /**
   * Get current playback status
   * 
   * @returns {object} Status object
   */
  getStatus() {
    return {
      isPlaying: this.isPlaying,
      isPaused: this.isPaused,
      queueLength: this.audioQueue.length
    };
  }
}

export default AudioPlayer;

