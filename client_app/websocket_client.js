/**
 * WebSocket Client Module
 * Handles connection to the Voice Bot API server
 */

class WebSocketClient {
    constructor(serverUrl, logger, uiManager) {
        this.serverUrl = serverUrl;
        this.log = logger;
        this.ui = uiManager;
        this.ws = null;
        this.audioQueue = [];
        this.isPlayingAudio = false;
        this.wasPlayingBeforePause = false;
        this.currentAudio = null;  // Track currently playing audio element
    }

    /**
     * Connect to WebSocket server
     */
    async connect() {
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.serverUrl);
                
                this.ws.onopen = () => {
                    this.log('✓ Connected to server', 'received');
                    this.ui.updateStatus('connected', 'Status: Connected ✓');
                    this.ui.setConnectionButtons(true);
                    resolve(this.ws);
                };
                
                this.ws.onmessage = (event) => {
                    this.handleMessage(event);
                };
                
                this.ws.onerror = (error) => {
                    this.log(`✗ WebSocket error`, 'error');
                    console.error('WebSocket error:', error);
                    reject(error);
                };
                
                this.ws.onclose = () => {
                    this.log('✗ Disconnected from server', 'error');
                    this.ui.updateStatus('disconnected', 'Status: Disconnected');
                    this.ui.setConnectionButtons(false);
                    this.ws = null;
                };
                
            } catch (error) {
                this.log(`✗ Connection error: ${error.message}`, 'error');
                reject(error);
            }
        });
    }

    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(event) {
        const data = JSON.parse(event.data);
        this.log(`← Received: ${data.event}`, 'received');
        
        if (data.event === 'play_audio' && data.audio) {
            // If we have a paused audio that we're no longer actively playing,
            // discard it—this indicates a fresh response is coming in.
            if (this.currentAudio && this.currentAudio.paused && !this.isPlayingAudio) {
                console.log('Discarding paused audio in favor of new chunk');
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0;
                this.currentAudio = null;
            }

            // Queue audio chunk for sequential playback (prevents overlapping)
            this.audioQueue.push(data.audio);
            this.log('🔊 Audio chunk queued', 'received');
            
            // Start playing if not already playing
            if (!this.isPlayingAudio) {
                this.playNextAudio();
            }
        } else if (data.event === 'stop_playback') {
            // Interruption detected - pause current audio (don't clear queue)
            this.pauseAudioPlayback();
            this.log('⏹️ Playback paused (interruption)', 'info');
        } else if (data.event === 'playback_reset') {
            // Server is discarding any buffered audio (interrupted response)
            this.stopAudioPlayback();
            this.wasPlayingBeforePause = false;
            this.log('⛔ Playback reset (stale audio cleared)', 'info');
        } else if (data.event === 'playback_resume') {
            // False alarm - resume playback from where we paused
            this.resumeAudioPlayback();
            this.log('▶️ Playback resumed (false alarm)', 'info');
        } else if (data.event === 'conversation_turn') {
            if (data.user) this.ui.addMessage('user', data.user);
            if (data.assistant) this.ui.addMessage('assistant', data.assistant);
        } else if (data.event === 'connected') {
            // Server welcome message
            this.log(`✓ ${data.message}`, 'received');
        } else if (data.event === 'status') {
            // Server status updates
            this.log(`ℹ️ ${data.message}`, 'info');
        }
    }

    /**
     * Play audio chunks sequentially from the queue
     */
    playNextAudio() {
        if (this.audioQueue.length === 0) {
            // Only notify server if we were playing (state change)
            if ((this.isPlayingAudio || this.wasPlayingBeforePause) && this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'client_playback_complete' }));
                console.log('→ Sent: client_playback_complete');
            }
            this.isPlayingAudio = false;
            this.wasPlayingBeforePause = false;
            return;
        }
        
        // Only notify server on FIRST chunk (state change from idle to playing)
        const wasNotPlaying = !this.isPlayingAudio;
        this.isPlayingAudio = true;
        this.wasPlayingBeforePause = false;
        
        if (wasNotPlaying && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'client_playback_started' }));
            console.log('→ Sent: client_playback_started');
        }
        
        const audioData = this.audioQueue.shift();
        
        try {
            const audio = new Audio('data:audio/mp3;base64,' + audioData);
            this.currentAudio = audio;  // Track current audio
            
            audio.onloadeddata = () => {
                console.log('Audio loaded successfully');
            };
            
            audio.onerror = (e) => {
                console.error('Audio error:', audio.error);
                this.log('✗ Audio playback error', 'error');
                this.currentAudio = null;
                // Continue with next audio even if this one fails
                this.playNextAudio();
            };
            
            audio.onended = () => {
                console.log('Audio finished playing');
                this.currentAudio = null;
                // Play next audio in queue (if any)
                // If queue is empty, playNextAudio will notify server
                this.playNextAudio();
            };
            
            audio.play().catch(err => {
                console.error('Audio playback failed:', err);
                this.log(`✗ Audio playback failed: ${err.message}`, 'error');
                this.currentAudio = null;
                // Continue with next audio even if this one fails
                this.playNextAudio();
            });
            
            this.log('▶️ Playing audio chunk', 'received');
        } catch (err) {
            console.error('Audio creation failed:', err);
            this.log('✗ Failed to create audio element', 'error');
            this.currentAudio = null;
            // Continue with next audio
            this.playNextAudio();
        }
    }

    /**
     * Pause audio playback (for interruptions - keeps queue intact for resume)
     */
    pauseAudioPlayback() {
        // Pause currently playing audio (don't reset, so we can resume)
        if (this.currentAudio) {
            this.currentAudio.pause();
            // Don't clear currentAudio - we'll resume it
            // Don't reset currentTime - resume from where we paused
        }
        
        // Don't clear the audio queue - we might resume this or future chunks
        const wasPlaying = this.isPlayingAudio || (this.currentAudio && !this.currentAudio.paused) || this.audioQueue.length > 0;
        this.wasPlayingBeforePause = wasPlaying;
        this.isPlayingAudio = false;
        
        console.log('Audio playback paused (queue preserved for resume)');
    }

    /**
     * Resume audio playback (for false alarms)
     */
    resumeAudioPlayback() {
        console.log('[Resume Audio] Resume audio playback requested');
        console.log(`[Resume Audio]   currentAudio: ${this.currentAudio ? 'exists' : 'null'}`);
        if (this.currentAudio) {
            console.log(`[Resume Audio]   currentAudio.paused: ${this.currentAudio.paused}`);
            console.log(`[Resume Audio]   currentAudio.ended: ${this.currentAudio.ended}`);
            console.log(`[Resume Audio]   currentAudio.currentTime: ${this.currentAudio.currentTime}`);
            console.log(`[Resume Audio]   currentAudio.duration: ${this.currentAudio.duration}`);
        }
        console.log(`[Resume Audio]   audioQueue.length: ${this.audioQueue.length}`);
        console.log(`[Resume Audio]   isPlayingAudio: ${this.isPlayingAudio}`);
        console.log(`[Resume Audio]   wasPlayingBeforePause: ${this.wasPlayingBeforePause}`);
        
        // Priority 1: Resume paused audio if it exists and is paused (not ended)
        if (this.currentAudio) {
            if (this.currentAudio.paused && !this.currentAudio.ended) {
                console.log('[Resume Audio] Resuming paused audio...');
                this.currentAudio.play()
                    .then(() => {
                        console.log('[Resume Audio] ✅ Resumed paused audio');
                        this.log('▶️ Resumed paused audio', 'info');
                        this.isPlayingAudio = true;  // Mark as playing
                        this.wasPlayingBeforePause = false;
                    })
                    .catch(err => {
                        console.error('[Resume Audio] Failed to resume audio:', err);
                        this.log(`✗ Failed to resume audio: ${err.message}`, 'error');
                        // If resume fails, clear currentAudio and try next audio from queue
                        this.currentAudio = null;
                        if (this.audioQueue.length > 0) {
                            console.log('[Resume Audio] Trying to play next audio from queue...');
                            this.playNextAudio();
                        } else {
                            this.isPlayingAudio = false;
                        }
                    });
                return;
            } else if (this.currentAudio.ended) {
                // Audio finished - clear it and continue with queue
                console.log('[Resume Audio] Current audio finished - clearing and checking queue');
                this.currentAudio = null;
            }
        }
        
        // Priority 2: Start playing from queue if we have audio queued
        // This handles the case where:
        // - Audio finished during interruption
        // - Audio was paused and then finished
        // - There's more audio in the queue that wasn't played yet
        if (this.audioQueue.length > 0) {
            console.log('[Resume Audio] Starting playback from queue (has audio queued)');
            this.isPlayingAudio = true;  // Mark as playing
            this.wasPlayingBeforePause = false;
            this.playNextAudio();
            return;
        }
        
        // Priority 3: No audio to resume (queue empty and nothing paused)
        // This can happen if:
        // - All audio was already sent and played before interruption
        // - Server hasn't sent more audio yet (agent might still be generating)
        console.log('[Resume Audio] No audio to resume (queue empty and nothing paused)');
        console.log('[Resume Audio] Checking if we should notify server...');
        
        // If we were playing before interruption but now have nothing to resume,
        // it means audio finished playing. Notify server that playback is complete.
        // This helps the server understand that there's nothing to resume.
        if ((this.isPlayingAudio || this.wasPlayingBeforePause) && this.ws && this.ws.readyState === WebSocket.OPEN) {
            // We were playing, but there's nothing to resume - audio must have finished
            console.log('[Resume Audio] Notifying server that playback is complete (nothing to resume)');
            this.ws.send(JSON.stringify({ type: 'client_playback_complete' }));
            console.log('→ Sent: client_playback_complete');
            this.isPlayingAudio = false;
            this.wasPlayingBeforePause = false;
        } else {
            // We weren't playing, so there's nothing to notify
            console.log('[Resume Audio] Not playing before - no notification needed');
            this.isPlayingAudio = false;
            this.wasPlayingBeforePause = false;
        }
        
        this.log('⚠️ No audio to resume (queue empty - waiting for server audio)', 'info');
        
        // Note: If server is still generating audio, it will send it soon
        // When audio arrives, playNextAudio() will be called automatically via handleMessage
    }

    /**
     * Stop audio playback completely (clears queue - for true interruptions)
     */
    stopAudioPlayback() {
        // Stop currently playing audio
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        
        // Clear the audio queue
        this.audioQueue = [];
        this.isPlayingAudio = false;
        
        console.log('Audio playback stopped and queue cleared');
    }

    /**
     * Disconnect from server
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
        // Clear audio queue on disconnect
        this.audioQueue = [];
        this.isPlayingAudio = false;
    }

    /**
     * Get WebSocket instance
     */
    getWebSocket() {
        return this.ws;
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}

// Export for use in main application
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketClient;
}

