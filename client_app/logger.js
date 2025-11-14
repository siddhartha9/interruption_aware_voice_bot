/**
 * Logger Module
 * Handles logging to the UI console
 */

class Logger {
    constructor(logDiv) {
        this.logDiv = logDiv;
    }

    /**
     * Log a message with timestamp and type
     */
    log(message, type = 'info') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        const timestamp = new Date().toLocaleTimeString();
        entry.textContent = `[${timestamp}] ${message}`;
        this.logDiv.appendChild(entry);
        this.logDiv.scrollTop = this.logDiv.scrollHeight;
        
        // Also log to console for debugging
        if (type === 'error') {
            console.error(message);
        } else if (type === 'sent' || type === 'received') {
            console.log(`%c${message}`, `color: ${type === 'sent' ? '#4fc3f7' : '#81c784'}`);
        } else {
            console.log(message);
        }
    }

    /**
     * Clear all logs
     */
    clear() {
        this.logDiv.innerHTML = '';
    }
}

// Export for use in main application
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Logger;
}

