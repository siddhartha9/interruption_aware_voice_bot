/**
 * Client-Side WebSocket Handler
 * 
 * Manages WebSocket connection and protocol with the voice bot server.
 */

import AudioRecorder from './audio_recorder.js';
import AudioPlayer from './audio_player.js';

class VoiceBotClient {
  constructor(serverUrl, options = {}) {
    this.serverUrl = serverUrl;
    this.options = options;
    
    // WebSocket
    this.ws = null;
    this.isConnected = false;
    
    // Audio components
    this.recorder = new AudioRecorder({
      sampleRate: options.sampleRate || 16000,
      vadOptions: options.vadOptions || {},
      onSpeechStart: () => this.handleSpeechStart(),
      onSpeechEnd: (audio) => this.handleSpeechEnd(audio)
    });
    
    this.player = new AudioPlayer({
      sampleRate: options.playbackSampleRate || 24000
    });
    
    // Callbacks
    this.onConnected = options.onConnected || (() => {});
    this.onDisconnected = options.onDisconnected || (() => {});
    this.onError = options.onError || ((error) => console.error(error));
    this.onTranscript = options.onTranscript || (() => {});
    this.onAgentResponse = options.onAgentResponse || (() => {});
    
    console.log('[VoiceBotClient] Initialized');
  }
  
  /**
   * Connect to the server
   */
  async connect() {
    try {
      this.ws = new WebSocket(this.serverUrl);
      
      this.ws.onopen = () => {
        this.isConnected = true;
        console.log('[WebSocket] Connected to server');
        this.onConnected();
      };
      
      this.ws.onclose = () => {
        this.isConnected = false;
        console.log('[WebSocket] Disconnected from server');
        this.onDisconnected();
      };
      
      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        this.onError(error);
      };
      
      this.ws.onmessage = (event) => {
        this.handleServerMessage(event.data);
      };
      
    } catch (error) {
      console.error('[WebSocket] Failed to connect:', error);
      this.onError(error);
      throw error;
    }
  }
  
  /**
   * Disconnect from server
   */
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected = false;
  }
  
  /**
   * Start recording
   */
  async startRecording() {
    try {
      await this.recorder.start();
      console.log('[VoiceBotClient] Recording started');
    } catch (error) {
      console.error('[VoiceBotClient] Failed to start recording:', error);
      this.onError(error);
      throw error;
    }
  }
  
  /**
   * Stop recording
   */
  stopRecording() {
    this.recorder.stop();
    console.log('[VoiceBotClient] Recording stopped');
  }
  
  /**
   * Handle speech start event from VAD
   */
  handleSpeechStart() {
    console.log('[VoiceBotClient] User started speaking');
    
    // Pause current playback immediately (no server round-trip)
    this.player.pause();
    
    // Notify server
    this.sendEvent({
      type: 'speech_start',
      timestamp: Date.now()
    });
  }
  
  /**
   * Handle speech end event from VAD
   * 
   * @param {Float32Array} audioData - Complete audio buffer
   */
  async handleSpeechEnd(audioData) {
    console.log('[VoiceBotClient] User stopped speaking');
    
    try {
      // Convert audio to base64
      const base64Audio = await this.recorder.float32ArrayToBase64(audioData);
      
      // Send to server
      this.sendEvent({
        type: 'speech_end',
        audio: base64Audio,
        timestamp: Date.now()
      });
      
    } catch (error) {
      console.error('[VoiceBotClient] Failed to process audio:', error);
      this.onError(error);
    }
  }
  
  /**
   * Send event to server
   * 
   * @param {object} event - Event object
   */
  sendEvent(event) {
    if (!this.isConnected) {
      console.warn('[WebSocket] Not connected, cannot send event');
      return;
    }
    
    try {
      this.ws.send(JSON.stringify(event));
    } catch (error) {
      console.error('[WebSocket] Failed to send event:', error);
      this.onError(error);
    }
  }
  
  /**
   * Handle message from server
   * 
   * @param {string} data - Message data
   */
  async handleServerMessage(data) {
    try {
      const message = JSON.parse(data);
      
      switch (message.event) {
        case 'play_audio':
          // Play audio chunk from server
          await this.player.play(message.audio);
          break;
        
        case 'playback_pause':
          // Server requests pause (backup, client should already be paused)
          this.player.pause();
          break;
        
        case 'playback_resume':
          // Server says false alarm, resume playback
          this.player.resume();
          break;
        
        case 'transcript':
          // Server sent transcript
          console.log('[Server] Transcript:', message.text);
          this.onTranscript(message.text);
          break;
        
        case 'agent_response':
          // Server sent agent text (for display)
          console.log('[Server] Agent:', message.text);
          this.onAgentResponse(message.text);
          break;
        
        case 'error':
          // Server sent error
          console.error('[Server] Error:', message.message);
          this.onError(new Error(message.message));
          break;
        
        default:
          console.warn('[Server] Unknown event type:', message.event);
      }
      
    } catch (error) {
      console.error('[VoiceBotClient] Failed to handle server message:', error);
      this.onError(error);
    }
  }
  
  /**
   * Get current status
   * 
   * @returns {object} Status object
   */
  getStatus() {
    return {
      connected: this.isConnected,
      recording: this.recorder.isRecording,
      playback: this.player.getStatus()
    };
  }
}

export default VoiceBotClient;

