/**
 * UI Manager Module
 * Handles all UI updates and interactions
 */

class UIManager {
    constructor() {
        // Cache DOM elements
        this.statusDiv = document.getElementById('status');
        this.vadStatus = document.getElementById('vadStatus');
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.listenBtn = document.getElementById('listenBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.conversation = document.getElementById('conversation');
        this.logDiv = document.getElementById('log');
    }

    /**
     * Update connection status indicator
     */
    updateStatus(state, message) {
        const indicator = this.statusDiv.querySelector('.indicator');
        this.statusDiv.className = `status ${state}`;
        
        const iconMap = {
            'disconnected': 'red',
            'connected': 'green',
            'listening': 'yellow'
        };
        
        const iconClass = iconMap[state] || 'red';
        indicator.className = `indicator ${iconClass}`;
        this.statusDiv.innerHTML = `<span class="indicator ${iconClass}"></span>${message}`;
    }

    /**
     * Update VAD status message
     */
    updateVADStatus(message) {
        this.vadStatus.textContent = message;
    }

    /**
     * Add message to conversation
     */
    addMessage(role, content) {
        const message = document.createElement('div');
        message.className = `message ${role}`;
        
        const label = document.createElement('div');
        label.className = 'label';
        label.textContent = role === 'user' ? 'You' : role === 'assistant' ? 'Bot' : 'System';
        
        const text = document.createElement('div');
        text.textContent = content;
        
        message.appendChild(label);
        message.appendChild(text);
        this.conversation.appendChild(message);
        this.conversation.scrollTop = this.conversation.scrollHeight;
    }

    /**
     * Update connection button states
     */
    setConnectionButtons(connected) {
        this.connectBtn.disabled = connected;
        this.disconnectBtn.disabled = !connected;
        this.listenBtn.disabled = !connected;
    }

    /**
     * Update listening button states
     */
    setListeningButtons(listening) {
        this.listenBtn.disabled = listening;
        this.stopBtn.disabled = !listening;
    }

    /**
     * Clear conversation
     */
    clearConversation() {
        this.conversation.innerHTML = `
            <div class="message system">
                <div class="label">System</div>
                <div>Ready to start. Click "Connect" and then "Start Listening"</div>
            </div>
        `;
    }

    /**
     * Clear log
     */
    clearLog() {
        this.logDiv.innerHTML = '';
    }
}

// Export for use in main application
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIManager;
}

