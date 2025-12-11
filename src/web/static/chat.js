/**
 * Chat application JavaScript
 * Handles user input, SSE streaming, and citation rendering
 */

const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const queryInput = document.getElementById('queryInput');
const submitBtn = document.getElementById('submitBtn');
const newChatBtn = document.getElementById('newChatBtn');
const podcastFilter = document.getElementById('podcastFilter');

let isProcessing = false;
let conversationHistory = []; // Store conversation history
let abortController = null; // For request cancellation

/**
 * Load podcasts for the filter dropdown
 */
async function loadPodcasts() {
    try {
        const response = await fetch('/api/podcasts');
        if (!response.ok) {
            console.error('Failed to load podcasts');
            return;
        }
        const data = await response.json();

        // Populate dropdown
        if (data.podcasts && data.podcasts.length > 0) {
            data.podcasts.forEach(podcast => {
                const option = document.createElement('option');
                option.value = podcast.id;
                option.textContent = podcast.title;
                podcastFilter.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading podcasts:', error);
    }
}

/**
 * Add a user message to the chat
 */
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message flex justify-end';
    messageDiv.innerHTML = `
        <div class="bg-primary text-white rounded-lg px-4 py-3 max-w-2xl shadow-sm">
            <p class="text-sm">${escapeHtml(text)}</p>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

/**
 * Add an assistant message (streaming) to the chat
 */
function addAssistantMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message flex justify-start';
    messageDiv.innerHTML = `
        <div class="bg-white rounded-lg px-4 py-3 max-w-2xl shadow-sm border border-gray-200">
            <div class="text-sm text-gray-800 markdown-content assistant-text"></div>
            <div class="citations-container mt-3"></div>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

/**
 * Add a typing indicator
 */
function addTypingIndicator() {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.id = 'typingIndicator';
    indicatorDiv.className = 'message flex justify-start';
    indicatorDiv.innerHTML = `
        <div class="bg-white rounded-lg px-4 py-3 shadow-sm border border-gray-200">
            <div class="typing-indicator flex gap-1">
                <span class="w-2 h-2 bg-gray-400 rounded-full"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full"></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(indicatorDiv);
    scrollToBottom();
}

/**
 * Remove typing indicator
 */
function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

/**
 * Render citations below the message
 * Handles both podcast (P prefix) and web (W prefix) citations
 * Also renders Google search entry point if provided (required by ToS)
 */
function renderCitations(container, citations, searchEntryPoint) {
    if ((!citations || citations.length === 0) && !searchEntryPoint) {
        return;
    }

    // Separate podcast and web citations
    const podcastCitations = citations ? citations.filter(c => c.source_type === 'podcast') : [];
    const webCitations = citations ? citations.filter(c => c.source_type === 'web') : [];

    // Render podcast citations
    const podcastHtml = podcastCitations.map(citation => {
        const refId = citation.ref_id;
        const metadata = citation.metadata || {};
        const parts = [];
        if (metadata.podcast && metadata.episode) {
            parts.push(`${metadata.podcast} - ${metadata.episode}`);
        } else if (metadata.podcast) {
            parts.push(metadata.podcast);
        } else if (metadata.episode) {
            parts.push(metadata.episode);
        } else if (citation.title) {
            // Clean up filename: remove _transcription.txt suffix and format
            let cleanTitle = citation.title
                .replace(/_transcription\.txt$/i, '')
                .replace(/[-_]/g, ' ')
                .trim();
            parts.push(cleanTitle);
        }
        const titleText = parts.length > 0 ? parts.join(' - ') : 'Podcast Source';
        const dateText = metadata.release_date ? `(${metadata.release_date})` : '';

        return `
            <div class="citation-card bg-blue-50 border border-blue-200 rounded-md px-3 py-2">
                <span class="font-semibold text-blue-600 text-sm">[${refId}]</span>
                <span class="text-sm text-gray-800">${escapeHtml(titleText)}</span>
                ${dateText ? `<span class="text-xs text-gray-500 ml-1">${escapeHtml(dateText)}</span>` : ''}
            </div>
        `;
    }).join('');

    // Render web citations (simplified - just show domain as clickable link)
    const webHtml = webCitations.map(citation => {
        const refId = citation.ref_id;
        // Title from Google is typically just the domain (e.g., "example.com")
        const domain = citation.title || 'Web Source';
        // URL is now in metadata for consistency with podcast citations
        const metadata = citation.metadata || {};
        const url = metadata.url || '';

        return `
            <div class="citation-card bg-green-50 border border-green-200 rounded-md px-3 py-2 inline-block mr-2 mb-1">
                <span class="font-semibold text-green-600 text-sm">[${refId}]</span>
                ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="text-sm text-green-700 hover:underline">${escapeHtml(domain)}</a>` : `<span class="text-sm text-gray-800">${escapeHtml(domain)}</span>`}
            </div>
        `;
    }).join('');

    // Build the full citations section
    let html = '<div class="border-t border-gray-200 pt-3 mt-2">';

    // Podcast sources section
    if (podcastHtml) {
        html += `
            <p class="text-xs font-semibold text-gray-600 mb-2">PODCAST SOURCES:</p>
            <div class="space-y-2 mb-3">
                ${podcastHtml}
            </div>
        `;
    }

    // Web sources section (if we have web citations or search entry point)
    if (webHtml || searchEntryPoint) {
        html += `<p class="text-xs font-semibold text-gray-600 mb-2">WEB SOURCES:</p>`;

        if (webHtml) {
            html += `<div class="mb-2">${webHtml}</div>`;
        }

        // Google search entry point (required by ToS for grounding)
        if (searchEntryPoint) {
            html += `<div class="google-search-suggestions mt-2">${searchEntryPoint}</div>`;
        }
    }

    html += '</div>';
    container.innerHTML = html;
}

/**
 * Show error message
 */
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'message';
    errorDiv.innerHTML = `
        <div class="bg-red-50 border border-red-200 rounded-lg px-4 py-3 shadow-sm">
            <p class="text-sm text-red-800">
                <strong>Error:</strong> ${escapeHtml(message)}
            </p>
        </div>
    `;
    chatMessages.appendChild(errorDiv);
    scrollToBottom();
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Update the status display during search
 */
function updateStatusDisplay(container, agent, message, isComplete = false, isThought = false) {
    // Get or create status container
    let statusContainer = container.querySelector('.status-container');
    if (!statusContainer) {
        statusContainer = document.createElement('div');
        statusContainer.className = 'status-container space-y-2';
        container.innerHTML = '';
        container.appendChild(statusContainer);
    }

    // Agent icons and colors
    const agentConfig = {
        'podcast': { icon: '🎙️', color: 'blue', label: 'Podcast Search' },
        'web': { icon: '🌐', color: 'green', label: 'Web Search' },
        'synthesizer': { icon: '🔄', color: 'purple', label: 'Synthesizer' },
        'tool': { icon: '🔧', color: 'gray', label: 'Tool' },
        'agent': { icon: '🤖', color: 'gray', label: 'Agent' }
    };

    const config = agentConfig[agent] || agentConfig['agent'];

    if (isThought) {
        // Show agent thought in a subtle way
        let thoughtEl = statusContainer.querySelector(`.thought-${agent}`);
        if (!thoughtEl) {
            thoughtEl = document.createElement('div');
            thoughtEl.className = `thought-${agent} text-xs text-gray-500 italic pl-6 border-l-2 border-${config.color}-200 mt-1`;
            statusContainer.appendChild(thoughtEl);
        }
        thoughtEl.textContent = message;
    } else {
        // Show agent status
        const statusId = `status-${agent}`;
        let statusEl = statusContainer.querySelector(`#${statusId}`);

        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.id = statusId;
            statusEl.className = `flex items-center gap-2 text-sm`;
            statusContainer.appendChild(statusEl);
        }

        const checkmark = isComplete ? '✓' : '';
        const spinnerClass = isComplete ? '' : 'animate-pulse';
        const textColor = isComplete ? 'text-gray-400' : `text-${config.color}-600`;

        statusEl.innerHTML = `
            <span class="${spinnerClass}">${config.icon}</span>
            <span class="${textColor}">${escapeHtml(message)}</span>
            <span class="text-green-500">${checkmark}</span>
        `;
    }
}

/**
 * Clear conversation and reset UI
 */
function clearConversation() {
    if (isProcessing) {
        // Cancel ongoing request
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
        isProcessing = false;
        submitBtn.disabled = false;
        queryInput.disabled = false;
        submitBtn.textContent = 'Send';
        removeTypingIndicator();
    }

    // Clear conversation history
    conversationHistory = [];

    // Clear chat messages except welcome message
    const welcomeMessage = chatMessages.querySelector('.message');
    chatMessages.innerHTML = '';
    if (welcomeMessage) {
        chatMessages.appendChild(welcomeMessage);
    }

    // Focus input
    queryInput.focus();
}

/**
 * Handle form submission
 */
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (isProcessing) {
        return;
    }

    const query = queryInput.value.trim();
    if (!query) {
        return;
    }

    // Disable input while processing
    isProcessing = true;
    submitBtn.disabled = true;
    queryInput.disabled = true;
    submitBtn.textContent = 'Sending...';

    // Add user message
    addUserMessage(query);

    // Add to conversation history
    conversationHistory.push({
        role: 'user',
        content: query
    });

    queryInput.value = '';

    // Add typing indicator
    addTypingIndicator();

    try {
        // Create abort controller for request cancellation
        abortController = new AbortController();

        // Create assistant message container
        removeTypingIndicator();
        const assistantMessageDiv = addAssistantMessage();
        const textContainer = assistantMessageDiv.querySelector('.assistant-text');
        const citationsContainer = assistantMessageDiv.querySelector('.citations-container');

        let fullText = '';

        // Get selected podcast filter
        const selectedPodcastId = podcastFilter.value ? parseInt(podcastFilter.value) : null;

        // Use fetch for POST with SSE streaming
        const requestBody = {
            query: query,
            history: conversationHistory.slice(0, -1) // All messages except current query
        };
        if (selectedPodcastId) {
            requestBody.podcast_id = selectedPodcastId;
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
            signal: abortController.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let buffer = '';

        // Read the stream
        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            // Split on blank lines to get individual events
            const parts = buffer.split(/\n\n+/);

            // Keep the last incomplete part in buffer
            buffer = parts.pop() || '';

            for (const part of parts) {
                if (!part.trim()) continue;

                // Parse event and data from each part
                let eventType = '';
                let eventData = '';

                const lines = part.split('\n');
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('event:')) {
                        eventType = trimmed.substring(6).trim();
                    } else if (trimmed.startsWith('data:')) {
                        eventData = trimmed.substring(5).trim();
                    }
                }

                if (eventData && eventType) {
                    try {
                        const data = JSON.parse(eventData);

                        if (eventType === 'token') {
                            fullText += data.token;
                            textContainer.innerHTML = fullText;
                            scrollToBottom();
                        } else if (eventType === 'citations') {
                            textContainer.innerHTML = fullText;
                            renderCitations(citationsContainer, data.citations, data.search_entry_point);
                            scrollToBottom();
                        } else if (eventType === 'status') {
                            // Handle status updates
                            if (data.phase === 'searching') {
                                textContainer.innerHTML = '<div class="status-container"><span class="text-gray-500 italic">Starting search...</span></div>';
                            } else if (data.phase === 'responding') {
                                textContainer.innerHTML = '';
                            } else if (data.agent && data.status === 'started') {
                                // Agent started
                                updateStatusDisplay(textContainer, data.agent, data.message);
                            } else if (data.agent && data.status === 'complete') {
                                // Agent completed
                                updateStatusDisplay(textContainer, data.agent, data.message, true);
                            } else if (data.tool) {
                                // Tool being called
                                updateStatusDisplay(textContainer, 'tool', data.message);
                            } else if (data.thought) {
                                // Agent thought/intermediate output
                                updateStatusDisplay(textContainer, data.agent || 'agent', data.thought, false, true);
                            }
                            scrollToBottom();
                        } else if (eventType === 'done') {
                            // Add assistant response to history
                            conversationHistory.push({
                                role: 'assistant',
                                content: fullText
                            });
                        } else if (eventType === 'error') {
                            throw new Error(data.error || 'An error occurred');
                        }
                    } catch (parseError) {
                        console.error('Failed to parse SSE data:', eventData, parseError);
                    }
                }
            }
        }

        isProcessing = false;
        submitBtn.disabled = false;
        queryInput.disabled = false;
        submitBtn.textContent = 'Send';
        queryInput.focus();

    } catch (error) {
        console.error('Error:', error);
        removeTypingIndicator();

        // Don't show error for aborted requests
        if (error.name !== 'AbortError') {
            showError(error.message || 'An unexpected error occurred.');
        }

        isProcessing = false;
        submitBtn.disabled = false;
        queryInput.disabled = false;
        submitBtn.textContent = 'Send';
        abortController = null;
    }
});

// Handle new chat button
if (newChatBtn) {
    newChatBtn.addEventListener('click', () => {
        if (confirm('Start a new conversation? This will clear the current chat.')) {
            clearConversation();
        }
    });
}

/**
 * Get URL parameter by name
 */
function getUrlParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * Initialize page: load podcasts and set filter from URL if present
 */
async function initPage() {
    await loadPodcasts();

    // Check for podcast filter in URL (from podcasts grid page)
    const podcastId = getUrlParam('podcast');
    if (podcastId) {
        podcastFilter.value = podcastId;
        // Clear the URL parameter
        window.history.replaceState({}, '', '/');
    }

    queryInput.focus();
}

// Initialize on page load
initPage();
