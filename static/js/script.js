class ChatInterface {
    constructor() {
        this.currentConversationId = 1;
        this.isTyping = false;
        this.isSidebarOpen = window.innerWidth > 768;
        this.apiEndpoint = 'http://localhost:8000/chat';
        
        this.initializeEventListeners();
        this.autoResizeTextarea();
        this.updateSidebarState();
    }
    
    initializeEventListeners() {
        const chatInput = document.getElementById('chatInput');
        const mobileOverlay = document.getElementById('mobileOverlay');
        
        // Handle Enter key
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        chatInput.addEventListener('input', () => {
            this.autoResizeTextarea();
        });
        
        // Mobile overlay click
        mobileOverlay.addEventListener('click', () => {
            this.closeSidebar();
        });
        
        // Window resize
        window.addEventListener('resize', () => {
            this.updateSidebarState();
        });
    }
    
    autoResizeTextarea() {
        const textarea = document.getElementById('chatInput');
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }
    
    toggleSidebar() {
        this.isSidebarOpen = !this.isSidebarOpen;
        this.updateSidebarState();
    }
    
    closeSidebar() {
        this.isSidebarOpen = false;
        this.updateSidebarState();
    }
    
    updateSidebarState() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('mobileOverlay');
        
        if (window.innerWidth <= 768) {
            // Mobile mode
            if (this.isSidebarOpen) {
                sidebar.classList.add('open');
                overlay.classList.add('show');
            } else {
                sidebar.classList.remove('open');
                overlay.classList.remove('show');
            }
        } else {
            // Desktop mode
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            this.isSidebarOpen = true;
        }
    }
    
    selectConversation(id) {
        // Update active conversation
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        event.target.classList.add('active');
        
        this.currentConversationId = id;
        this.loadConversation(id);
        
        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            this.closeSidebar();
        }
    }
    
    loadConversation(id) {
        // Clear current messages
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = '';
        
        // Load conversation messages (mock data for now)
        this.addMessage(`Welcome to Conversation ${id}!`, 'assistant');
        
        // In real implementation, you'd fetch from your backend:
        // this.fetchConversationHistory(id);
    }
    
    startNewConversation() {
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = '';
        this.addMessage("Hello! I'm your AI assistant. How can I help you today?", 'assistant');
        
        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            this.closeSidebar();
        }
    }
    
    async sendMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        
        if (!message || this.isTyping) return;
        
        // Add user message
        this.addMessage(message, 'user');
        input.value = '';
        this.autoResizeTextarea();
        
        // Show typing indicator
        this.showTyping();
        
        try {
            const response = await this.callAPI(message);
            this.hideTyping();
            this.addMessage(response, 'assistant');
        } catch (error) {
            this.hideTyping();
            this.addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
            console.error('Chat API error:', error);
        }
    }
    
    async callAPI(message) {
        // Mock API for now
        return new Promise((resolve) => {
            setTimeout(() => {
                const responses = [
                    `That's an interesting point about "${message}". Let me think about that...`,
                    `I understand you're asking about "${message}". Here's what I think...`,
                    `Thanks for sharing that. Regarding "${message}", I'd say...`,
                    `That's a great question about "${message}". In my experience...`
                ];
                resolve(responses[Math.floor(Math.random() * responses.length)]);
            }, 1000 + Math.random() * 2000);
        });
    }
    
    addMessage(text, sender) {
        const messagesContainer = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = text;
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeDiv);
        messagesContainer.appendChild(messageDiv);
        
        this.scrollToBottom();
    }
    
    showTyping() {
        this.isTyping = true;
        const messagesContainer = document.getElementById('chatMessages');
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message typing';
        typingDiv.id = 'typingIndicator';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = 'AI is typing...';
        
        typingDiv.appendChild(contentDiv);
        messagesContainer.appendChild(typingDiv);
        this.scrollToBottom();
        
        document.getElementById('sendButton').disabled = true;
    }
    
    hideTyping() {
        this.isTyping = false;
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        document.getElementById('sendButton').disabled = false;
    }
    
    scrollToBottom() {
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}
        

// Global functions for inline event handlers
let chatInterface;

function toggleSidebar() {
    chatInterface.toggleSidebar();
    console.log("Toggle Side bar");
}

function selectConversation(id) {
    chatInterface.selectConversation(id);
}

function startNewConversation() {
    chatInterface.startNewConversation();
}

function sendMessage() {
    chatInterface.sendMessage();
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    chatInterface = new ChatInterface();
    console.log("chat interface initilized");
});