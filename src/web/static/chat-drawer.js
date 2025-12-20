/**
 * ChatDrawer - Reusable chat drawer component for multi-scope podcast chat
 *
 * Supports chat scopes:
 * - episode: Chat scoped to single episode
 * - podcast: Chat scoped to all episodes in a podcast
 * - subscriptions: Chat scoped to user's subscribed podcasts
 * - all: Global chat across all podcasts
 *
 * Usage:
 *   const drawer = new ChatDrawer({
 *       scope: 'episode',  // 'episode' | 'podcast' | 'subscriptions' | 'all'
 *       episodeId: '123',  // Required for 'episode' scope
 *       podcastId: 456,    // Required for 'podcast' scope
 *       subscribedOnly: true,  // Required for 'subscriptions' scope
 *       contextTitle: 'Episode Title'  // Optional subtitle for drawer header
 *   });
 *   drawer.init();
 */
class ChatDrawer {
    constructor(options = {}) {
        this.scope = options.scope || 'all';
        this.episodeId = options.episodeId || null;
        this.podcastId = options.podcastId || null;
        this.subscribedOnly = options.subscribedOnly || false;
        this.contextTitle = options.contextTitle || '';

        // DOM elements (will be set in init)
        this.backdrop = null;
        this.drawer = null;
        this.messages = null;
        this.input = null;
        this.submitBtn = null;
        this.headerTitle = null;
        this.headerSubtitle = null;

        // State
        this.isProcessing = false;

        // Event listener references for cleanup
        this._backdropClickHandler = null;
        this._closeBtnClickHandler = null;
        this._formSubmitHandler = null;
        this._keydownHandler = null;
    }

    /**
     * Initialize the drawer component
     */
    init() {
        // Clean up any existing drawer first
        this._cleanupExistingDrawer();
        this._createDrawerHTML();
        this._attachEventListeners();
    }

    /**
     * Clean up existing drawer elements if they exist
     */
    _cleanupExistingDrawer() {
        const existingBackdrop = document.getElementById('drawerBackdrop');
        const existingDrawer = document.getElementById('chatDrawer');

        if (existingBackdrop) {
            existingBackdrop.remove();
        }
        if (existingDrawer) {
            existingDrawer.remove();
        }
    }

    /**
     * Destroy the drawer and clean up all resources
     */
    destroy() {
        // Remove event listeners
        if (this.backdrop && this._backdropClickHandler) {
            this.backdrop.removeEventListener('click', this._backdropClickHandler);
        }

        const closeBtn = document.getElementById('drawerCloseBtn');
        if (closeBtn && this._closeBtnClickHandler) {
            closeBtn.removeEventListener('click', this._closeBtnClickHandler);
        }

        const form = document.getElementById('drawerChatForm');
        if (form && this._formSubmitHandler) {
            form.removeEventListener('submit', this._formSubmitHandler);
        }

        if (this._keydownHandler) {
            document.removeEventListener('keydown', this._keydownHandler);
        }

        // Remove DOM elements
        if (this.backdrop) {
            this.backdrop.remove();
        }
        if (this.drawer) {
            this.drawer.remove();
        }

        // Reset body overflow
        document.body.style.overflow = '';

        // Null out references
        this.backdrop = null;
        this.drawer = null;
        this.messages = null;
        this.input = null;
        this.submitBtn = null;
        this.headerTitle = null;
        this.headerSubtitle = null;
        this._backdropClickHandler = null;
        this._closeBtnClickHandler = null;
        this._formSubmitHandler = null;
        this._keydownHandler = null;
    }

    /**
     * Create drawer HTML structure and append to body
     */
    _createDrawerHTML() {
        const drawerHTML = `
            <!-- Chat Drawer Backdrop -->
            <div id="drawerBackdrop" class="drawer-backdrop"></div>

            <!-- Chat Drawer -->
            <div id="chatDrawer" class="drawer shadow-xl">
                <!-- Drawer Header -->
                <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <div class="flex-1 min-w-0">
                        <h3 id="drawerHeaderTitle" class="font-semibold text-gray-900 truncate"></h3>
                        <p id="drawerHeaderSubtitle" class="text-sm text-gray-500 truncate"></p>
                    </div>
                    <button
                        id="drawerCloseBtn"
                        class="ml-2 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
                        title="Close"
                    >
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>

                <!-- Messages Area -->
                <div id="drawerMessages" class="drawer-messages space-y-4">
                    <!-- Welcome message -->
                    <div class="bg-gray-100 rounded-lg p-3 text-sm text-gray-700">
                        <p id="drawerWelcome">Ask me anything. I'll search the podcasts and provide answers with citations.</p>
                    </div>
                </div>

                <!-- Input Form -->
                <form id="drawerChatForm" class="p-4 border-t border-gray-200 bg-white">
                    <div class="flex gap-2">
                        <input
                            type="text"
                            id="drawerInput"
                            placeholder="Ask a question..."
                            class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm"
                            autocomplete="off"
                            required
                        />
                        <button
                            type="submit"
                            id="drawerSubmitBtn"
                            class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                            </svg>
                        </button>
                    </div>
                </form>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', drawerHTML);

        // Get DOM references
        this.backdrop = document.getElementById('drawerBackdrop');
        this.drawer = document.getElementById('chatDrawer');
        this.messages = document.getElementById('drawerMessages');
        this.input = document.getElementById('drawerInput');
        this.submitBtn = document.getElementById('drawerSubmitBtn');
        this.headerTitle = document.getElementById('drawerHeaderTitle');
        this.headerSubtitle = document.getElementById('drawerHeaderSubtitle');
        this.welcomeMessage = document.getElementById('drawerWelcome');

        // Set header title based on scope
        this._updateHeaderText();
    }

    /**
     * Update header text based on scope
     */
    _updateHeaderText() {
        const scopeTitles = {
            'episode': 'Ask about this episode',
            'podcast': 'Ask about this podcast',
            'subscriptions': 'Ask about your podcasts',
            'all': 'Ask about any podcast'
        };

        const scopeWelcomes = {
            'episode': 'Ask me anything about this episode. I\'ll search the transcript and provide answers with citations.',
            'podcast': 'Ask me anything about this podcast. I\'ll search all episodes and provide answers with citations.',
            'subscriptions': 'Ask me anything about your subscribed podcasts. I\'ll search across all your podcasts.',
            'all': 'Ask me anything about any podcast in the library. I\'ll search and provide answers with citations.'
        };

        this.headerTitle.textContent = scopeTitles[this.scope] || scopeTitles.all;
        this.headerSubtitle.textContent = this.contextTitle;
        this.welcomeMessage.textContent = scopeWelcomes[this.scope] || scopeWelcomes.all;
    }

    /**
     * Attach event listeners
     */
    _attachEventListeners() {
        // Close on backdrop click
        this._backdropClickHandler = () => this.close();
        this.backdrop.addEventListener('click', this._backdropClickHandler);

        // Close button
        const closeBtn = document.getElementById('drawerCloseBtn');
        this._closeBtnClickHandler = () => this.close();
        closeBtn.addEventListener('click', this._closeBtnClickHandler);

        // Form submission
        const form = document.getElementById('drawerChatForm');
        this._formSubmitHandler = (e) => this._handleSubmit(e);
        form.addEventListener('submit', this._formSubmitHandler);

        // Close on Escape key
        this._keydownHandler = (e) => {
            if (e.key === 'Escape' && this.drawer.classList.contains('open')) {
                this.close();
            }
        };
        document.addEventListener('keydown', this._keydownHandler);
    }

    /**
     * Open the chat drawer
     */
    open() {
        this.backdrop.classList.add('open');
        this.drawer.classList.add('open');
        document.body.style.overflow = 'hidden';
        this.input.focus();
    }

    /**
     * Close the chat drawer
     */
    close() {
        this.backdrop.classList.remove('open');
        this.drawer.classList.remove('open');
        document.body.style.overflow = '';
    }

    /**
     * Update context title (for dynamic updates)
     */
    setContextTitle(title) {
        this.contextTitle = title;
        this.headerSubtitle.textContent = title;
    }

    /**
     * Handle form submission
     */
    async _handleSubmit(e) {
        e.preventDefault();
        if (this.isProcessing) return;

        const query = this.input.value.trim();
        if (!query) return;

        this.isProcessing = true;
        this.submitBtn.disabled = true;
        this.input.value = '';

        // Add user message
        this._addMessage(query, 'user');

        // Add typing indicator
        const typingId = this._addTypingIndicator();

        try {
            // Build request body based on scope
            const requestBody = { query };

            if (this.scope === 'episode' && this.episodeId) {
                requestBody.episode_id = this.episodeId;
            } else if (this.scope === 'podcast' && this.podcastId) {
                requestBody.podcast_id = this.podcastId;
            } else if (this.scope === 'subscriptions' && this.subscribedOnly) {
                requestBody.subscribed_only = true;
            }
            // For 'all' scope, no additional parameters needed

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Process SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let responseText = '';
            let citations = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split(/\n\n+/);
                buffer = parts.pop() || '';

                for (const part of parts) {
                    const lines = part.split('\n');
                    let eventType = '';
                    let eventData = '';

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith('event:')) {
                            eventType = trimmed.substring(6).trim();
                        } else if (trimmed.startsWith('data:')) {
                            eventData = trimmed.substring(5).trim();
                        }
                    }

                    if (!eventType || !eventData) continue;

                    try {
                        const data = JSON.parse(eventData);

                        if (eventType === 'token') {
                            responseText += data.token || '';
                        } else if (eventType === 'citations') {
                            citations = data.citations || [];
                        } else if (eventType === 'error') {
                            throw new Error(data.error || 'Unknown error');
                        }
                    } catch (parseError) {
                        // Skip parse errors for incomplete events
                    }
                }
            }

            // Remove typing indicator and add response
            this._removeTypingIndicator(typingId);
            this._addMessage(responseText, 'assistant', citations);

        } catch (error) {
            console.error('Chat error:', error);
            this._removeTypingIndicator(typingId);
            this._addMessage(`Error: ${error.message}`, 'error');
        } finally {
            this.isProcessing = false;
            this.submitBtn.disabled = false;
        }
    }

    /**
     * Add a message to the drawer
     */
    _addMessage(text, role, citations = []) {
        const messageDiv = document.createElement('div');

        if (role === 'user') {
            messageDiv.className = 'bg-primary text-white rounded-lg p-3 text-sm ml-8';
            messageDiv.textContent = text;
        } else if (role === 'error') {
            messageDiv.className = 'bg-red-100 text-red-700 rounded-lg p-3 text-sm';
            messageDiv.textContent = text;
        } else {
            messageDiv.className = 'bg-gray-100 rounded-lg p-3 text-sm text-gray-700';

            // Render markdown (sanitized to prevent XSS)
            const contentDiv = document.createElement('div');
            contentDiv.className = 'chat-markdown';
            contentDiv.innerHTML = this._safeMarkdownToHtml(text);
            messageDiv.appendChild(contentDiv);

            // Add citations if present
            if (citations.length > 0) {
                const citationsDiv = document.createElement('div');
                citationsDiv.className = 'mt-3 pt-3 border-t border-gray-200 text-xs text-gray-500';
                citationsDiv.innerHTML = '<p class="font-medium mb-2">Sources:</p>' +
                    citations.filter(c => c.source_type === 'podcast').map(c =>
                        `<p class="truncate">${this._escapeHtml(c.metadata?.podcast || '')} - ${this._escapeHtml(c.metadata?.episode || c.title || '')}</p>`
                    ).join('');
                messageDiv.appendChild(citationsDiv);
            }
        }

        this.messages.appendChild(messageDiv);
        this.messages.scrollTop = this.messages.scrollHeight;
    }

    /**
     * Add typing indicator
     */
    _addTypingIndicator() {
        const id = 'typing-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'bg-gray-100 rounded-lg p-3 text-sm text-gray-500 flex gap-1';
        div.innerHTML = '<span class="typing-dot">●</span><span class="typing-dot">●</span><span class="typing-dot">●</span>';
        this.messages.appendChild(div);
        this.messages.scrollTop = this.messages.scrollHeight;
        return id;
    }

    /**
     * Remove typing indicator
     */
    _removeTypingIndicator(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    /**
     * Escape HTML to prevent XSS
     */
    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Safely render markdown to sanitized HTML.
     * Uses DOMPurify to prevent XSS attacks from AI/upstream content.
     * Falls back to plain text if DOMPurify is unavailable.
     */
    _safeMarkdownToHtml(text) {
        const rawText = text || 'No response received.';

        // Check if marked.js is available
        if (typeof marked === 'undefined' || !marked.parse) {
            console.warn('Marked.js not available, falling back to plain text rendering');
            return this._escapeHtml(rawText);
        }

        const parsedHtml = marked.parse(rawText);

        // Use DOMPurify if available, otherwise fall back to textContent (safe but loses formatting)
        if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
            return DOMPurify.sanitize(parsedHtml, {
                ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                ALLOWED_ATTR: ['href', 'target', 'rel'],
                ALLOW_DATA_ATTR: false,
            });
        }

        // Fallback: return escaped text (loses markdown formatting but safe)
        console.warn('DOMPurify not available, falling back to plain text rendering');
        return this._escapeHtml(rawText);
    }
}
