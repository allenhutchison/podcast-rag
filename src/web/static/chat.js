/**
 * Chat Page JavaScript
 * Handles conversation management, messaging, and scope selection
 */

// State
let currentConversationId = null;
let currentScope = 'subscriptions';
let selectedPodcastId = null;
let selectedEpisodeId = null;
let isStreaming = false;
let podcasts = [];

// DOM Elements
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const scopeSelect = document.getElementById('scopeSelect');
const podcastPicker = document.getElementById('podcastPicker');
const podcastSelect = document.getElementById('podcastSelect');
const episodePicker = document.getElementById('episodePicker');
const episodeSelect = document.getElementById('episodeSelect');
const conversationList = document.getElementById('conversationList');
const messagesArea = document.getElementById('messagesArea');
const welcomeState = document.getElementById('welcomeState');
const messagesContainer = document.getElementById('messagesContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const mobileTitle = document.getElementById('mobileTitle');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Use auth.js for authentication and user menu
    const user = await requireAuth();
    if (!user) return;
    updateUserUIWithAdmin(user);

    await loadConversations();
    await loadPodcasts();
    handleUrlParams();
});

// Load conversations
async function loadConversations() {
    try {
        const response = await fetch('/api/conversations', { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to load conversations');
        const data = await response.json();
        renderConversationList(data.conversations);
    } catch (error) {
        console.error('Error loading conversations:', error);
        conversationList.innerHTML = '<p class="text-sm text-red-500 p-2">Failed to load history</p>';
    }
}

// Render conversation list
function renderConversationList(conversations) {
    if (!conversations || conversations.length === 0) {
        conversationList.innerHTML = `
            <div class="empty-conversations">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
                </svg>
                <p class="text-sm">No conversations yet</p>
            </div>
        `;
        return;
    }

    conversationList.innerHTML = conversations.map(conv => {
        const title = conv.title || 'New conversation';
        const scopeLabel = getScopeLabel(conv.scope, conv.podcast_title, conv.episode_title);
        const isActive = conv.id === currentConversationId;
        const timeAgo = formatTimeAgo(new Date(conv.updated_at));

        return `
            <div class="conversation-item ${isActive ? 'active' : ''}"
                 onclick="loadConversation('${conv.id}')"
                 data-id="${conv.id}">
                <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0 flex-1">
                        <div class="title">${escapeHtml(title)}</div>
                        <div class="meta">${escapeHtml(scopeLabel)} &middot; ${timeAgo}</div>
                    </div>
                    <button
                        class="delete-btn p-1 text-gray-400 hover:text-red-500 rounded"
                        onclick="event.stopPropagation(); deleteConversation('${conv.id}')"
                        title="Delete conversation"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Load podcasts for dropdown
async function loadPodcasts() {
    try {
        const response = await fetch('/api/podcasts?include_stats=true', { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to load podcasts');
        podcasts = await response.json();

        podcastSelect.innerHTML = '<option value="">Select podcast...</option>' +
            podcasts.map(p => `<option value="${p.id}">${escapeHtml(p.title)}</option>`).join('');
    } catch (error) {
        console.error('Error loading podcasts:', error);
    }
}

// Load episodes for a podcast
async function loadEpisodes(podcastId) {
    try {
        const response = await fetch(`/api/podcasts/${podcastId}`, { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to load episodes');
        const data = await response.json();

        episodeSelect.innerHTML = '<option value="">Select episode...</option>' +
            data.episodes.map(e => `<option value="${e.id}">${escapeHtml(e.title)}</option>`).join('');
    } catch (error) {
        console.error('Error loading episodes:', error);
    }
}

// Handle URL parameters (for deep linking from podcast/episode pages)
function handleUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const scope = params.get('scope');
    const podcastId = params.get('podcast_id');
    const episodeId = params.get('episode_id');

    if (scope) {
        setScope(scope, podcastId, episodeId);
    }
}

// Set scope programmatically
function setScope(scope, podcastId = null, episodeId = null) {
    currentScope = scope;
    selectedPodcastId = podcastId;
    selectedEpisodeId = episodeId;

    scopeSelect.value = scope;
    handleScopeChange();

    if (podcastId) {
        podcastSelect.value = podcastId;
        handlePodcastChange();
    }
    if (episodeId) {
        episodeSelect.value = episodeId;
    }
}

// Handle scope dropdown change
function handleScopeChange() {
    const scope = scopeSelect.value;
    currentScope = scope;

    // Show/hide secondary pickers
    if (scope === 'podcast' || scope === 'episode') {
        podcastPicker.classList.remove('hidden');
        if (scope === 'episode') {
            episodePicker.classList.remove('hidden');
        } else {
            episodePicker.classList.add('hidden');
            selectedEpisodeId = null;
        }
    } else {
        podcastPicker.classList.add('hidden');
        episodePicker.classList.add('hidden');
        selectedPodcastId = null;
        selectedEpisodeId = null;
    }
}

// Handle podcast dropdown change
function handlePodcastChange() {
    selectedPodcastId = podcastSelect.value || null;

    if (currentScope === 'episode' && selectedPodcastId) {
        loadEpisodes(selectedPodcastId);
        episodePicker.classList.remove('hidden');
    }
}

// Handle episode dropdown change
function handleEpisodeChange() {
    selectedEpisodeId = episodeSelect.value || null;
}

// Create new conversation
async function createNewConversation() {
    // Validate scope selection
    if (currentScope === 'podcast' && !selectedPodcastId) {
        alert('Please select a podcast first');
        return;
    }
    if (currentScope === 'episode' && !selectedEpisodeId) {
        alert('Please select an episode first');
        return;
    }

    try {
        const body = {
            scope: currentScope,
            podcast_id: selectedPodcastId,
            episode_id: selectedEpisodeId
        };

        const response = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body)
        });

        if (!response.ok) throw new Error('Failed to create conversation');
        const conversation = await response.json();

        currentConversationId = conversation.id;
        await loadConversations();
        showMessagesView();
        updateMobileTitle(conversation.title || 'New Chat');

        // Close sidebar on mobile
        if (window.innerWidth < 640) {
            toggleSidebar();
        }
    } catch (error) {
        console.error('Error creating conversation:', error);
        alert('Failed to create conversation');
    }
}

// Load a conversation
async function loadConversation(conversationId) {
    try {
        const response = await fetch(`/api/conversations/${conversationId}`, { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to load conversation');
        const conversation = await response.json();

        currentConversationId = conversation.id;
        currentScope = conversation.scope;
        selectedPodcastId = conversation.podcast_id;
        selectedEpisodeId = conversation.episode_id;

        // Update scope selector
        scopeSelect.value = conversation.scope;
        handleScopeChange();
        if (conversation.podcast_id) {
            podcastSelect.value = conversation.podcast_id;
        }
        if (conversation.episode_id) {
            loadEpisodes(conversation.podcast_id).then(() => {
                episodeSelect.value = conversation.episode_id;
            });
        }

        // Render messages
        showMessagesView();
        renderMessages(conversation.messages);
        updateMobileTitle(conversation.title || 'Conversation');

        // Update active state in list
        document.querySelectorAll('.conversation-item').forEach(el => {
            el.classList.toggle('active', el.dataset.id === conversationId);
        });

        // Close sidebar on mobile
        if (window.innerWidth < 640) {
            toggleSidebar();
        }
    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

// Delete conversation
async function deleteConversation(conversationId) {
    if (!confirm('Delete this conversation?')) return;

    try {
        const response = await fetch(`/api/conversations/${conversationId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (!response.ok) throw new Error('Failed to delete conversation');

        if (currentConversationId === conversationId) {
            currentConversationId = null;
            showWelcomeState();
        }

        await loadConversations();
    } catch (error) {
        console.error('Error deleting conversation:', error);
        alert('Failed to delete conversation');
    }
}

// Show messages view
function showMessagesView() {
    welcomeState.classList.add('hidden');
    messagesContainer.classList.remove('hidden');
}

// Show welcome state
function showWelcomeState() {
    welcomeState.classList.remove('hidden');
    messagesContainer.classList.add('hidden');
    messagesContainer.innerHTML = '';
}

// Render messages
function renderMessages(messages) {
    messagesContainer.innerHTML = messages.map(msg => {
        const isUser = msg.role === 'user';
        return `
            <div class="message ${msg.role}">
                ${isUser ? escapeHtml(msg.content) : `<div class="chat-markdown">${safeMarkdownToHtml(msg.content)}</div>`}
                ${!isUser && msg.citations && msg.citations.length > 0 ? renderCitations(msg.citations) : ''}
            </div>
        `;
    }).join('');

    scrollToBottom();
}

// Render citations
function renderCitations(citations) {
    return `
        <div class="citations">
            ${citations.map(c => `
                <div class="citation">
                    <span class="citation-number">${c.index}</span>
                    <span class="citation-text">
                        ${escapeHtml(c.metadata.podcast)} - ${escapeHtml(c.metadata.episode)}
                        ${c.metadata.release_date ? `(${c.metadata.release_date})` : ''}
                    </span>
                </div>
            `).join('')}
        </div>
    `;
}

// Handle message submission
async function handleSubmit(event) {
    event.preventDefault();

    const content = messageInput.value.trim();
    if (!content || isStreaming) return;

    // Create conversation if needed
    if (!currentConversationId) {
        await createNewConversation();
        if (!currentConversationId) return; // Creation failed
    }

    // Add user message to UI
    showMessagesView();
    addMessageToUI(content, 'user');
    messageInput.value = '';

    // Show typing indicator
    const typingIndicator = addTypingIndicator();

    isStreaming = true;
    sendBtn.disabled = true;

    try {
        const response = await fetch(`/api/conversations/${currentConversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ content })
        });

        if (!response.ok) throw new Error('Failed to send message');

        // Stream response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantContent = '';
        let citations = [];
        let assistantMessageEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    const eventType = line.slice(7);
                    continue;
                }
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    try {
                        const parsed = JSON.parse(data);

                        if (parsed.token) {
                            // Remove typing indicator on first token
                            if (!assistantMessageEl) {
                                typingIndicator.remove();
                                assistantMessageEl = addMessageToUI('', 'assistant');
                            }
                            assistantContent += parsed.token;
                            updateAssistantMessage(assistantMessageEl, assistantContent);
                        } else if (parsed.citations) {
                            citations = parsed.citations;
                        }
                    } catch (e) {
                        // Ignore parse errors
                    }
                }
            }
        }

        // Add citations if any
        if (citations.length > 0 && assistantMessageEl) {
            const citationsHtml = renderCitations(citations);
            assistantMessageEl.insertAdjacentHTML('beforeend', citationsHtml);
        }

        // Refresh conversation list to update title
        await loadConversations();

    } catch (error) {
        console.error('Error sending message:', error);
        typingIndicator.remove();
        addMessageToUI('Sorry, there was an error processing your message. Please try again.', 'error');
    } finally {
        isStreaming = false;
        sendBtn.disabled = false;
    }
}

// Add message to UI
function addMessageToUI(content, role) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    if (role === 'user') {
        messageEl.textContent = content;
    } else if (role === 'error') {
        messageEl.className = 'message assistant';
        messageEl.innerHTML = `<div class="text-red-500">${escapeHtml(content)}</div>`;
    } else {
        messageEl.innerHTML = `<div class="chat-markdown">${safeMarkdownToHtml(content)}</div>`;
    }

    messagesContainer.appendChild(messageEl);
    scrollToBottom();
    return messageEl;
}

// Update assistant message during streaming
function updateAssistantMessage(el, content) {
    const markdownEl = el.querySelector('.chat-markdown');
    if (markdownEl) {
        markdownEl.innerHTML = safeMarkdownToHtml(content);
    }
    scrollToBottom();
}

// Add typing indicator
function addTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    messagesContainer.appendChild(indicator);
    scrollToBottom();
    return indicator;
}

// Scroll to bottom of messages
function scrollToBottom() {
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

// Toggle sidebar (mobile)
function toggleSidebar() {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('hidden');
}

// Update mobile title
function updateMobileTitle(title) {
    mobileTitle.textContent = title || 'Chat';
}

// Get scope label
function getScopeLabel(scope, podcastTitle, episodeTitle) {
    switch (scope) {
        case 'subscriptions':
            return 'My Subscriptions';
        case 'all':
            return 'All Podcasts';
        case 'podcast':
            return podcastTitle || 'Podcast';
        case 'episode':
            return episodeTitle || 'Episode';
        default:
            return scope;
    }
}

// Format time ago
function formatTimeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

// Escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Safe markdown to HTML (with DOMPurify sanitization)
function safeMarkdownToHtml(text) {
    if (!text) return '';

    // Configure marked for safe rendering
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });

    const html = marked.parse(text);

    // Sanitize with DOMPurify
    return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
        ALLOWED_ATTR: ['href', 'target', 'rel'],
        ADD_ATTR: ['target'],
        FORCE_BODY: true
    });
}
