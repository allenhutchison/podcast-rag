/**
 * Chat application JavaScript
 * Handles user input, SSE streaming, and citation rendering
 */

const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const queryInput = document.getElementById('queryInput');
const submitBtn = document.getElementById('submitBtn');

let isProcessing = false;
let conversationHistory = []; // Store conversation history

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
 */
function renderCitations(container, citations) {
    if (!citations || citations.length === 0) {
        return;
    }

    const citationsHtml = citations.map(citation => {
        const { index, metadata } = citation;
        const { podcast, episode, release_date } = metadata;

        // Build citation text
        const parts = [];
        if (podcast && episode) {
            parts.push(`${podcast} - ${episode}`);
        } else if (podcast) {
            parts.push(podcast);
        } else if (episode) {
            parts.push(episode);
        }

        const titleText = parts.length > 0 ? parts.join(' - ') : 'Unknown Source';
        const dateText = release_date ? `(${release_date})` : '';

        return `
            <div class="citation-card bg-gray-50 border border-gray-200 rounded-md px-3 py-2">
                <span class="font-semibold text-primary text-sm">[${index}]</span>
                <span class="text-sm text-gray-800">${escapeHtml(titleText)}</span>
                ${dateText ? `<span class="text-xs text-gray-500 ml-1">${escapeHtml(dateText)}</span>` : ''}
            </div>
        `;
    }).join('');

    container.innerHTML = `
        <div class="border-t border-gray-200 pt-3 mt-2">
            <p class="text-xs font-semibold text-gray-600 mb-2">SOURCES:</p>
            <div class="space-y-2">
                ${citationsHtml}
            </div>
        </div>
    `;
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
        // Create assistant message container
        removeTypingIndicator();
        const assistantMessageDiv = addAssistantMessage();
        const textContainer = assistantMessageDiv.querySelector('.assistant-text');
        const citationsContainer = assistantMessageDiv.querySelector('.citations-container');

        let fullText = '';

        // Use fetch for POST with SSE streaming
        console.log('Sending request with history:', conversationHistory.slice(0, -1));

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                history: conversationHistory.slice(0, -1) // All messages except current query
            })
        });

        console.log('Response status:', response.status);

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
                console.log('Stream done');
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
                            renderCitations(citationsContainer, data.citations);
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
        showError(error.message || 'An unexpected error occurred.');
        isProcessing = false;
        submitBtn.disabled = false;
        queryInput.disabled = false;
        submitBtn.textContent = 'Send';
    }
});

// Focus input on page load
queryInput.focus();
