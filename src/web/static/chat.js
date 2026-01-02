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

// Configure marked for safe rendering (once at module load)
marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false
});

// Streaming render state - tracks pending updates for debounced rendering
let pendingRender = null;
let lastRenderTime = 0;
const RENDER_INTERVAL_MS = 50; // Render at most every 50ms during streaming

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
        const data = await response.json();
        podcasts = data.podcasts || [];

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
async function handleUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const scope = params.get('scope');
    const podcastId = params.get('podcast_id');
    const episodeId = params.get('episode_id');

    if (scope) {
        await setScope(scope, podcastId, episodeId);
    }
}

// Set scope programmatically
async function setScope(scope, podcastId = null, episodeId = null) {
    currentScope = scope;
    selectedPodcastId = podcastId;
    selectedEpisodeId = episodeId;

    scopeSelect.value = scope;
    handleScopeChange();

    if (podcastId) {
        podcastSelect.value = podcastId;
        // For episode scope, load episodes and wait before setting the value
        if (scope === 'episode' && episodeId) {
            await loadEpisodes(podcastId);
            episodeSelect.value = episodeId;
        } else {
            handlePodcastChange();
        }
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

// Start a new conversation (resets state, conversation created lazily on first message)
function createNewConversation() {
    // Reset conversation state
    currentConversationId = null;

    // Clear messages and show welcome state
    messagesContainer.innerHTML = '';
    showWelcomeState();
    updateMobileTitle('New Chat');

    // Deselect any active conversation in sidebar
    document.querySelectorAll('.conversation-item').forEach(el => {
        el.classList.remove('active');
    });

    // Close sidebar on mobile
    if (window.innerWidth < 640) {
        toggleSidebar();
    }

    // Focus the input
    messageInput.focus();
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

// Add internal links to podcast/episode names in the response text
function addInternalLinks(content, citations) {
    // Build a mapping of names to links from citations
    const linkMap = [];

    for (const c of citations) {
        // Add podcast name → podcast link
        if (c.metadata && c.metadata.podcast && c.podcast_id) {
            linkMap.push({
                name: c.metadata.podcast,
                url: `/podcast.html?id=${c.podcast_id}`,
                type: 'podcast'
            });
        }
        // Add episode name → episode link (for transcript sources)
        if (c.metadata && c.metadata.episode && c.episode_id) {
            linkMap.push({
                name: c.metadata.episode,
                url: `/episode.html?id=${c.episode_id}`,
                type: 'episode'
            });
        }
    }

    // Sort by name length (longest first) to avoid partial matches
    linkMap.sort((a, b) => b.name.length - a.name.length);

    // Replace each name with a markdown link (only first occurrence to avoid duplicates)
    let result = content;
    const replaced = new Set();

    for (const item of linkMap) {
        if (replaced.has(item.name)) continue;

        // Escape special regex characters in the name
        const escapedName = item.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

        // Try to find and replace the name (only first occurrence)
        // Check for bold format first: **Name** or **Name:**
        const boldRegex = new RegExp(`(\\*\\*)(${escapedName})(:\\*\\*|\\*\\*)`, 'i');
        const boldMatch = result.match(boldRegex);

        if (boldMatch) {
            // Bold format: **Name** → **[Name](url)**
            const name = boldMatch[2];
            const suffix = boldMatch[3];
            const replacement = `**[${name}](${item.url})${suffix.replace('**', '')}**`;
            result = result.replace(boldRegex, replacement);
            replaced.add(item.name);
        } else {
            // Try standalone name (word boundary match)
            const standaloneRegex = new RegExp(`\\b(${escapedName})\\b`, 'i');
            const standaloneMatch = result.match(standaloneRegex);

            if (standaloneMatch) {
                // Check if it's already inside a markdown link [...](...)
                const idx = result.indexOf(standaloneMatch[0]);
                const before = result.substring(Math.max(0, idx - 50), idx);
                const after = result.substring(idx, Math.min(result.length, idx + standaloneMatch[0].length + 50));

                // Skip if already in a link (preceded by [ or followed by ]( patterns)
                if (!before.includes('[') || before.lastIndexOf(']') > before.lastIndexOf('[')) {
                    const name = standaloneMatch[1];
                    const replacement = `[${name}](${item.url})`;
                    result = result.replace(standaloneRegex, replacement);
                    replaced.add(item.name);
                }
            }
        }
    }

    return result;
}

// Render citations with links to internal podcast/episode pages
function renderCitations(citations) {
    return `
        <div class="citations">
            ${citations.map(c => {
                // Build the link based on source type and available IDs
                let linkHref = '#';
                let linkText = '';

                if (c.source_type === 'description' && c.podcast_id) {
                    // Podcast description - link to podcast page
                    linkHref = `/podcast.html?id=${c.podcast_id}`;
                    linkText = escapeHtml(c.metadata.podcast || c.title);
                } else if (c.episode_id) {
                    // Transcript - link to episode page
                    linkHref = `/episode.html?id=${c.episode_id}`;
                    const podcast = c.metadata.podcast ? escapeHtml(c.metadata.podcast) + ' - ' : '';
                    const episode = escapeHtml(c.metadata.episode || c.title);
                    const date = c.metadata.release_date ? ` (${c.metadata.release_date})` : '';
                    linkText = podcast + episode + date;
                } else if (c.podcast_id) {
                    // Fallback to podcast link if no episode_id
                    linkHref = `/podcast.html?id=${c.podcast_id}`;
                    linkText = escapeHtml(c.metadata.podcast || c.title);
                } else {
                    // No IDs available - just show text
                    linkText = escapeHtml(c.metadata.podcast || c.title);
                }

                return `
                    <div class="citation">
                        <span class="citation-number">${c.index}</span>
                        <a href="${linkHref}" class="citation-link">${linkText}</a>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

// Handle message submission
async function handleSubmit(event) {
    event.preventDefault();

    const content = messageInput.value.trim();
    if (!content || isStreaming) return;

    // Validate scope before showing UI feedback
    if (!currentConversationId) {
        if (currentScope === 'podcast' && !selectedPodcastId) {
            alert('Please select a podcast first');
            return;
        }
        if (currentScope === 'episode' && !selectedEpisodeId) {
            alert('Please select an episode first');
            return;
        }
    }

    // Show UI feedback immediately (before any async work)
    showMessagesView();
    addMessageToUI(content, 'user');
    messageInput.value = '';
    const typingIndicator = addTypingIndicator();

    isStreaming = true;
    sendBtn.disabled = true;

    try {
        // Create conversation if needed (after showing UI feedback)
        if (!currentConversationId) {
            const body = {
                scope: currentScope,
                podcast_id: selectedPodcastId,
                episode_id: selectedEpisodeId
            };

            const createResponse = await fetch('/api/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(body)
            });

            if (!createResponse.ok) throw new Error('Failed to create conversation');
            const conversation = await createResponse.json();

            currentConversationId = conversation.id;
            updateMobileTitle(conversation.title || 'New Chat');

            // Refresh sidebar in background (don't await)
            loadConversations().catch(e => console.error('Failed to refresh conversations:', e));
        }

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
        let buffer = '';  // Buffer to handle SSE events split across chunks

        // Track tool activity
        let toolActivityEl = null;
        let toolSteps = [];

        // Helper to update tool activity display
        function updateToolActivity() {
            if (!toolActivityEl) {
                // Create tool activity element before the typing indicator
                toolActivityEl = document.createElement('div');
                toolActivityEl.className = 'tool-activity';
                typingIndicator.parentNode.insertBefore(toolActivityEl, typingIndicator);
            }

            toolActivityEl.innerHTML = `
                <div class="tool-activity-header">🔍 Searching...</div>
                ${toolSteps.map(step => `
                    <div class="tool-step ${step.status}">
                        <span class="tool-icon">${step.status === 'running' ? '⏳' : step.success ? '✓' : '✗'}</span>
                        <span class="tool-text">${escapeHtml(step.text)}</span>
                    </div>
                `).join('')}
            `;
            scrollToBottom();
        }

        // Helper to parse a single SSE event and update state
        function processSSEEvent(event) {
            if (!event.trim()) return;

            // Parse SSE event - find the event type and data
            const lines = event.split('\n');
            let eventType = 'message';
            let eventData = null;

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    try {
                        eventData = JSON.parse(line.slice(6));
                    } catch (e) {
                        // Ignore parse errors
                    }
                }
            }

            if (!eventData) return;

            // Debug: log all events (use console.debug to avoid noise in production)
            console.debug('SSE Event:', eventType, eventData);

            if (eventType === 'tool_call') {
                // Show tool being called
                console.debug('Tool call received:', eventData);
                toolSteps.push({
                    tool: eventData.tool,
                    text: eventData.description || eventData.display_name,
                    status: 'running',
                    success: null
                });
                updateToolActivity();
            } else if (eventType === 'tool_result') {
                // Update the matching tool step
                const step = toolSteps.find(s => s.tool === eventData.tool && s.status === 'running');
                if (step) {
                    step.status = 'complete';
                    step.success = eventData.success;
                    step.text = eventData.summary || step.text;
                    updateToolActivity();
                }
            } else if (eventData.token) {
                // Remove typing indicator on first token, but keep tool activity visible
                if (!assistantMessageEl) {
                    typingIndicator.remove();
                    // Move tool activity before creating assistant message so it stays visible
                    assistantMessageEl = addMessageToUI('', 'assistant');
                    // If we have tool activity, move it inside the assistant message at the top
                    if (toolActivityEl && toolSteps.length > 0) {
                        toolActivityEl.classList.add('complete');
                        assistantMessageEl.insertBefore(toolActivityEl, assistantMessageEl.firstChild);
                    }
                }
                assistantContent += eventData.token;
                updateAssistantMessage(assistantMessageEl, assistantContent);
            } else if (eventData.citations) {
                citations = eventData.citations;
            }
        }

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // Accumulate chunks in buffer
            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE events (delimited by double newline)
            const events = buffer.split('\n\n');
            // Keep the last incomplete event in buffer
            buffer = events.pop() || '';

            for (const event of events) {
                processSSEEvent(event);
            }
        }

        // Process any remaining buffer content (final event without trailing \n\n)
        if (buffer.trim()) {
            processSSEEvent(buffer);
        }

        // Add internal links to podcast/episode names based on citations
        if (citations.length > 0) {
            assistantContent = addInternalLinks(assistantContent, citations);
        }

        // Force final render to ensure all content is displayed with proper markdown
        if (assistantMessageEl && assistantContent) {
            finalizeAssistantMessage(assistantMessageEl, assistantContent);
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

// Update assistant message during streaming (throttled to avoid excessive re-renders)
function updateAssistantMessage(el, content, forceRender = false) {
    const markdownEl = el.querySelector('.chat-markdown');
    if (!markdownEl) return;

    const now = Date.now();
    const timeSinceLastRender = now - lastRenderTime;

    // Clear any pending render since we have new content
    if (pendingRender) {
        clearTimeout(pendingRender);
        pendingRender = null;
    }

    // Force render, or enough time has passed - render immediately
    if (forceRender || timeSinceLastRender >= RENDER_INTERVAL_MS) {
        markdownEl.innerHTML = safeMarkdownToHtml(content);
        lastRenderTime = now;
        scrollToBottom();
    } else {
        // Schedule a render for later to ensure content eventually displays
        pendingRender = setTimeout(() => {
            markdownEl.innerHTML = safeMarkdownToHtml(content);
            lastRenderTime = Date.now();
            scrollToBottom();
            pendingRender = null;
        }, RENDER_INTERVAL_MS - timeSinceLastRender);
    }
}

// Force final render after streaming completes
function finalizeAssistantMessage(el, content) {
    // Clear any pending render
    if (pendingRender) {
        clearTimeout(pendingRender);
        pendingRender = null;
    }
    // Force immediate render
    updateAssistantMessage(el, content, true);
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

    const html = marked.parse(text);

    // Sanitize with DOMPurify
    return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
        ALLOWED_ATTR: ['href', 'target', 'rel'],
        ADD_ATTR: ['target'],
        FORCE_BODY: true
    });
}
