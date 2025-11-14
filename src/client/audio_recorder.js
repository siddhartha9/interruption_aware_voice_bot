/**
 * Client-Side Audio Recorder
 * 
 * Captures microphone audio and integrates with VAD to buffer speech segments.
 */

import ClientVAD from './vad.js';

class AudioRecorder {
  constructor(options = {}) {
    this.sampleRate = options.sampleRate || 16000;
    this.vadOptions = options.vadOptions || {};
    this.onSpeechStart = options.onSpeechStart || (() => {});
    this.onSpeechEnd = options.onSpeechEnd || (() => {});
    
    // Audio context and nodes
    this.audioContext = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.processorNode = null;
    
    // VAD
    this.vad = new ClientVAD(this.vadOptions);
    
    // Audio buffering
    this.audioBuffer = [];
    this.isRecording = false;
    
    console.log('[AudioRecorder] Initialized');
  }
  
  /**
   * Start recording from microphone
   */
  async start() {
    try {
      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: this.sampleRate,
        }
      });
      
      // Create audio context
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: this.sampleRate
      });
      
      // Create source from microphone
      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      
      // Create processor node (ScriptProcessorNode or AudioWorklet)
      // Note: ScriptProcessorNode is deprecated, use AudioWorklet in production
      const bufferSize = 4096;
      this.processorNode = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
      
      // Process audio chunks
      this.processorNode.onaudioprocess = (event) => {
        const audioData = event.inputBuffer.getChannelData(0);
        this.processAudioChunk(audioData);
      };
      
      // Connect nodes
      this.sourceNode.connect(this.processorNode);
      this.processorNode.connect(this.audioContext.destination);
      
      this.isRecording = true;
      console.log('[AudioRecorder] Recording started');
      
    } catch (error) {
      console.error('[AudioRecorder] Failed to start recording:', error);
      throw error;
    }
  }
  
  /**
   * Stop recording
   */
  stop() {
    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode = null;
    }
    
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.isRecording = false;
    console.log('[AudioRecorder] Recording stopped');
  }
  
  /**
   * Process a single audio chunk with VAD
   * 
   * @param {Float32Array} audioData - Audio samples
   */
  processAudioChunk(audioData) {
    if (!this.isRecording) return;
    
    // Run VAD on this chunk
    const vadEvent = this.vad.processChunk(audioData);
    
    if (vadEvent === 'START') {
      // User started speaking
      this.audioBuffer = [new Float32Array(audioData)];
      this.onSpeechStart();
      
    } else if (vadEvent === 'SPEECH') {
      // Continue buffering speech
      this.audioBuffer.push(new Float32Array(audioData));
      
    } else if (vadEvent === 'END') {
      // User stopped speaking
      const completeAudio = this.concatenateBuffers(this.audioBuffer);
      this.onSpeechEnd(completeAudio);
      this.audioBuffer = [];
    }
  }
  
  /**
   * Concatenate audio buffers into single Float32Array
   * 
   * @param {Array<Float32Array>} buffers - Array of audio buffers
   * @returns {Float32Array} Concatenated audio
   */
  concatenateBuffers(buffers) {
    const totalLength = buffers.reduce((sum, buf) => sum + buf.length, 0);
    const result = new Float32Array(totalLength);
    
    let offset = 0;
    for (const buffer of buffers) {
      result.set(buffer, offset);
      offset += buffer.length;
    }
    
    return result;
  }
  
  /**
   * Convert Float32Array to WAV format
   * 
   * @param {Float32Array} audioData - Audio samples
   * @returns {Blob} WAV audio blob
   */
  float32ArrayToWav(audioData) {
    const numChannels = 1;
    const sampleRate = this.sampleRate;
    const bitsPerSample = 16;
    
    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    
    const dataLength = audioData.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);
    
    // WAV header
    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // fmt chunk size
    view.setUint16(20, 1, true); // audio format (PCM)
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true); // byte rate
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(36, 'data');
    view.setUint32(40, dataLength, true);
    
    // Convert float samples to 16-bit PCM
    let offset = 44;
    for (let i = 0; i < audioData.length; i++) {
      const sample = Math.max(-1, Math.min(1, audioData[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
      offset += 2;
    }
    
    return new Blob([buffer], { type: 'audio/wav' });
  }
  
  /**
   * Convert Float32Array to base64 encoded WAV
   * 
   * @param {Float32Array} audioData - Audio samples
   * @returns {Promise<string>} Base64 encoded WAV
   */
  async float32ArrayToBase64(audioData) {
    const wavBlob = this.float32ArrayToWav(audioData);
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(wavBlob);
    });
  }
}

export default AudioRecorder;

