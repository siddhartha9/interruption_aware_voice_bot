/**
 * Silero VAD Integration Module
 * Handles speech detection using Silero VAD neural network
 */

class SileroVADManager {
    constructor(websocket, logger, uiManager) {
        this.ws = websocket;
        this.log = logger;
        this.ui = uiManager;
        
        this.myvad = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isListening = false;
        this.isRecording = false;
    }

    /**
     * Initialize and start Silero VAD
     */
    async start() {
        try {
            this.log('🎤 Initializing Silero VAD...', 'info');
            this.ui.addMessage('system', 'Loading AI-powered voice detection...');
            this.ui.updateVADStatus('⏳ VAD: Loading model...');
            
            // Initialize Silero VAD with callbacks
            this.myvad = await vad.MicVAD.new({
                onSpeechStart: () => this.handleSpeechStart(),
                onSpeechEnd: (audio) => this.handleSpeechEnd(audio),
                
                // VAD Configuration
                positiveSpeechThreshold: 0.85,  // Higher = less sensitive
                negativeSpeechThreshold: 0.70,  // End threshold
                minSpeechFrames: 5,             // Min frames to confirm speech
                redemptionFrames: 8,            // ~0.5s silence detection
                preSpeechPadFrames: 1,          // Include frames before speech
            });
            
            // Setup MediaRecorder with VAD's audio stream
            await this.setupMediaRecorder(this.myvad.stream);
            
            // Start VAD
            this.myvad.start();
            this.isListening = true;
            
            this.ui.updateStatus('connected', 'Status: Ready - Speak when ready! 🎤');
            this.ui.updateVADStatus('✅ VAD: Active (AI listening)');
            this.ui.setListeningButtons(true);
            
            this.log('✅ Silero VAD activated!', 'received');
            this.ui.addMessage('system', '✅ AI voice detection active. Speak naturally!');
            
            return true;
            
        } catch (error) {
            this.log(`✗ VAD error: ${error.message}`, 'error');
            this.ui.addMessage('system', `Error: ${error.message}`);
            this.ui.updateVADStatus('❌ VAD: Failed to load');
            console.error('VAD Error:', error);
            throw error;
        }
    }

    /**
     * Setup MediaRecorder for audio capture
     */
    async setupMediaRecorder(stream) {
        // Try WAV first (best compatibility), fallback to WebM
        let mimeType = 'audio/wav';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'audio/webm;codecs=opus';
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = 'audio/webm';
            }
        }
        console.log(`[Silero VAD] Using mimeType: ${mimeType}`);
        
        this.mediaRecorder = new MediaRecorder(stream, {
            mimeType: mimeType
        });
        
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                this.audioChunks.push(event.data);
            }
        };
        
        this.mediaRecorder.onstop = async () => {
            if (this.audioChunks.length === 0) {
                this.log('⚠️ No audio recorded', 'error');
                return;
            }
            
            // Use the same mimeType that was used for recording
            const audioBlob = new Blob(this.audioChunks, { type: this.mediaRecorder.mimeType });
            this.log(`📦 Audio blob: ${audioBlob.size} bytes (${this.mediaRecorder.mimeType})`, 'info');
            
            // Convert to base64
            const reader = new FileReader();
            reader.readAsDataURL(audioBlob);
            reader.onloadend = () => {
                const base64Audio = reader.result.split(',')[1];
                
                // Send speech_end with audio to server
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'speech_end',
                        audio: base64Audio
                    }));
                    this.log('→ Sent: speech_end with audio', 'sent');
                    this.ui.addMessage('user', 'Processing...');
                }
                
                // Clear for next recording
                this.audioChunks = [];
            };
        };
    }

    /**
     * Handle speech start event from Silero VAD
     */
    handleSpeechStart() {
        this.log('🎤 [Silero VAD] Speech detected!', 'sent');
        
        // ALWAYS send speech_start to server for interruption detection
        // Even if we're already recording (could be a new interruption)
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'speech_start' }));
            this.log('→ Sent: speech_start', 'sent');
            this.ui.addMessage('system', '🎤 Listening...');
            this.ui.updateStatus('listening', 'Status: Recording... 🎤');
            this.ui.updateVADStatus('🎤 VAD: Recording speech');
        }
        
        // Handle MediaRecorder state
        if (!this.isRecording) {
            this.isRecording = true;
            this.audioChunks = [];
            
            // Start MediaRecorder
            if (this.mediaRecorder && this.mediaRecorder.state === 'inactive') {
                this.mediaRecorder.start(100);
                this.log('📼 Recording started', 'info');
            }
        } else {
            // Already recording - restart for new utterance
            this.log('📼 Restarting recording for new speech', 'info');
            
            // Stop current recording
            if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                this.mediaRecorder.stop();
            }
            
            // Clear old chunks and start fresh
            this.audioChunks = [];
            
            // Restart recording
            setTimeout(() => {
                if (this.mediaRecorder && this.mediaRecorder.state === 'inactive') {
                    this.mediaRecorder.start(100);
                    this.log('📼 Recording restarted', 'info');
                }
            }, 50); // Small delay to allow stop to complete
        }
    }

    /**
     * Handle speech end event from Silero VAD
     */
    handleSpeechEnd(audio) {
        this.log('🤫 [Silero VAD] Speech ended', 'info');
        
        // Always reset recording state
        this.isRecording = false;
        
        // Stop MediaRecorder if still recording
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
            this.log('🛑 Recording stopped', 'info');
        }
        
        this.ui.updateStatus('connected', 'Status: Processing...');
        this.ui.updateVADStatus('✅ VAD: Ready (waiting for speech)');
    }

    /**
     * Stop VAD and clean up
     */
    stop() {
        if (this.myvad) {
            this.myvad.pause();
            this.isListening = false;
            this.isRecording = false;
            
            this.ui.updateStatus('connected', 'Status: Connected ✓');
            this.ui.updateVADStatus('⏹️ VAD: Paused');
            this.ui.setListeningButtons(false);
            
            this.log('🛑 Stopped listening', 'info');
            this.ui.addMessage('system', 'Stopped listening');
        }
    }

    /**
     * Destroy VAD instance
     */
    destroy() {
        if (this.myvad) {
            this.myvad.pause();
            this.myvad = null;
        }
        this.isListening = false;
        this.isRecording = false;
    }
}

// Export for use in main application
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SileroVADManager;
}

