/**
 * Main Application Script
 * Orchestrates all modules
 */

class VoiceBotApp {
    constructor() {
        // Initialize modules
        const logDiv = document.getElementById('log');
        this.logger = new Logger(logDiv);
        this.log = (msg, type) => this.logger.log(msg, type);
        
        this.ui = new UIManager();
        this.wsClient = new WebSocketClient('ws://127.0.0.1:8000/ws', this.log.bind(this.logger), this.ui);
        this.vadManager = null;
    }

    /**
     * Connect to server
     */
    async connect() {
        try {
            await this.wsClient.connect();
        } catch (error) {
            this.log(`✗ Connection failed: ${error.message}`, 'error');
            alert('Failed to connect to server. Make sure the server is running on port 8000.');
        }
    }

    /**
     * Disconnect from server
     */
    disconnect() {
        if (this.vadManager) {
            this.vadManager.destroy();
            this.vadManager = null;
        }
        this.wsClient.disconnect();
    }

    /**
     * Start listening (activate VAD)
     */
    async startListening() {
        try {
            if (!this.vadManager) {
                const ws = this.wsClient.getWebSocket();
                this.vadManager = new SileroVADManager(ws, this.log.bind(this.logger), this.ui);
            }
            await this.vadManager.start();
        } catch (error) {
            this.log(`✗ Failed to start VAD: ${error.message}`, 'error');
            alert('Failed to initialize Silero VAD. Please refresh and try again.');
        }
    }

    /**
     * Stop listening (pause VAD)
     */
    stopListening() {
        if (this.vadManager) {
            this.vadManager.stop();
        }
    }
}

// Initialize application when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new VoiceBotApp();
    console.log('✅ Voice Bot App initialized');
});

