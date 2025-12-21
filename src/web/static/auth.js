/**
 * Authentication utilities for Podcast RAG frontend.
 *
 * Provides:
 * - checkAuth(): Check if user is authenticated
 * - requireAuth(): Redirect to login if not authenticated
 * - logout(): Log out and redirect to login
 * - updateUserUI(user): Update header with user info
 */

/**
 * Check if the current user is authenticated.
 *
 * @returns {Promise<Object|null>} User object if authenticated, null otherwise
 */
async function checkAuth() {
    try {
        const response = await fetch('/auth/me', {
            credentials: 'include'
        });

        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch (error) {
        console.error('Auth check failed:', error);
        return null;
    }
}

/**
 * Require authentication, redirecting to login if not authenticated.
 *
 * @returns {Promise<Object|null>} User object if authenticated, null if redirecting
 */
async function requireAuth() {
    const user = await checkAuth();
    if (!user) {
        // Redirect to login page
        window.location.href = '/login.html';
        return null;
    }
    return user;
}

/**
 * Log out the current user.
 * Redirects to the logout endpoint which clears the session cookie.
 */
function logout() {
    window.location.href = '/auth/logout';
}

/**
 * Validate and sanitize a picture URL.
 * Only allows https URLs or same-origin URLs.
 *
 * @param {string} url - The URL to validate
 * @returns {string} The validated URL or empty string if invalid
 */
function validatePictureUrl(url) {
    if (!url) return '';
    try {
        const parsed = new URL(url, window.location.origin);
        // Allow https URLs (Google profile pictures) or same-origin
        if (parsed.protocol === 'https:' || parsed.origin === window.location.origin) {
            return parsed.href;
        }
    } catch (e) {
        // Invalid URL
    }
    return '';
}

/**
 * Update the user info display in the page header.
 * Uses DOM methods to prevent XSS attacks.
 * Creates a dropdown menu triggered by clicking the user picture.
 *
 * @param {Object} user - User object from auth check
 * @param {string} user.name - User's display name
 * @param {string} user.email - User's email
 * @param {string} user.picture - URL to user's profile picture
 * @param {boolean} user.is_admin - Whether user is an admin (optional)
 * @param {Object} options - Display options
 * @param {boolean} options.showAdminLink - Whether to show admin link for admin users
 */
function updateUserUI(user, options = {}) {
    const { showAdminLink = false } = options;
    const userInfoContainer = document.getElementById('userInfo');
    if (!userInfoContainer) return;

    // Clear existing content
    userInfoContainer.innerHTML = '';

    // Create relative container for dropdown positioning
    const container = document.createElement('div');
    container.className = 'relative';

    // Create button with user picture
    const userButton = document.createElement('button');
    userButton.className = 'flex items-center gap-2 focus:outline-none hover:opacity-80 transition-opacity';
    userButton.id = 'userMenuButton';

    // Create and configure image element
    const validPictureUrl = validatePictureUrl(user.picture);
    if (validPictureUrl) {
        const img = document.createElement('img');
        img.src = validPictureUrl;
        img.alt = user.name || user.email || 'User';
        img.className = 'w-8 h-8 rounded-full border-2 border-gray-200';
        img.referrerPolicy = 'no-referrer';
        img.addEventListener('error', function() {
            // Fallback to initials if image fails
            const initials = document.createElement('div');
            initials.className = 'w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center text-sm font-medium';
            initials.textContent = (user.name || user.email || '?').charAt(0).toUpperCase();
            this.replaceWith(initials);
        });
        userButton.appendChild(img);
    } else {
        // No picture - show initials
        const initials = document.createElement('div');
        initials.className = 'w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center text-sm font-medium';
        initials.textContent = (user.name || user.email || '?').charAt(0).toUpperCase();
        userButton.appendChild(initials);
    }

    // Add dropdown arrow
    const arrow = document.createElement('svg');
    arrow.className = 'w-4 h-4 text-gray-500';
    arrow.setAttribute('fill', 'none');
    arrow.setAttribute('stroke', 'currentColor');
    arrow.setAttribute('viewBox', '0 0 24 24');
    arrow.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>';
    userButton.appendChild(arrow);

    container.appendChild(userButton);

    // Create dropdown menu
    const dropdown = document.createElement('div');
    dropdown.id = 'userMenuDropdown';
    dropdown.className = 'hidden absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50';

    // Add user name/email header
    const header = document.createElement('div');
    header.className = 'px-4 py-2 border-b border-gray-200';
    const nameDiv = document.createElement('div');
    nameDiv.className = 'text-sm font-medium text-gray-900 truncate';
    nameDiv.textContent = user.name || '';
    const emailDiv = document.createElement('div');
    emailDiv.className = 'text-xs text-gray-500 truncate';
    emailDiv.textContent = user.email || '';
    header.appendChild(nameDiv);
    if (user.email && user.name) {
        header.appendChild(emailDiv);
    }
    dropdown.appendChild(header);

    // Add Settings link
    const settingsLink = document.createElement('a');
    settingsLink.href = '/settings.html';
    settingsLink.className = 'block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors';
    settingsLink.textContent = 'Settings';
    dropdown.appendChild(settingsLink);

    // Add admin link for admin users (if enabled)
    if (showAdminLink && isAdmin(user)) {
        const adminLink = document.createElement('a');
        adminLink.href = '/admin.html';
        adminLink.className = 'block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors';
        adminLink.textContent = 'Admin';
        dropdown.appendChild(adminLink);
    }

    // Add separator
    const separator = document.createElement('div');
    separator.className = 'border-t border-gray-200 my-1';
    dropdown.appendChild(separator);

    // Add Sign Out button
    const signOutBtn = document.createElement('button');
    signOutBtn.className = 'block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors';
    signOutBtn.textContent = 'Sign Out';
    signOutBtn.addEventListener('click', logout);
    dropdown.appendChild(signOutBtn);

    container.appendChild(dropdown);
    userInfoContainer.appendChild(container);

    // Toggle dropdown on button click
    userButton.addEventListener('click', function(e) {
        e.stopPropagation();
        dropdown.classList.toggle('hidden');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!container.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    });
}

/**
 * Initialize authentication for a page.
 * Call this in DOMContentLoaded to check auth and update UI.
 *
 * @returns {Promise<Object|null>} User object if authenticated
 */
async function initAuth() {
    const user = await requireAuth();
    if (user) {
        updateUserUI(user);
    }
    return user;
}

/**
 * Check if the current user is an admin.
 *
 * @param {Object} user - User object from auth check
 * @returns {boolean} True if user is an admin
 */
function isAdmin(user) {
    return user && user.is_admin === true;
}

/**
 * Require admin access, redirecting to home if not admin.
 *
 * @returns {Promise<Object|null>} User object if admin, null if redirecting
 */
async function requireAdmin() {
    const user = await requireAuth();
    if (!user) return null;

    if (!isAdmin(user)) {
        window.location.href = '/';
        return null;
    }
    return user;
}

/**
 * Update the user info display with admin link for admin users.
 * Wrapper for updateUserUI with showAdminLink enabled.
 *
 * @param {Object} user - User object from auth check
 */
function updateUserUIWithAdmin(user) {
    updateUserUI(user, { showAdminLink: true });
}

/**
 * Initialize authentication for a page with admin link support.
 * Call this in DOMContentLoaded to check auth and update UI with admin link.
 *
 * @returns {Promise<Object|null>} User object if authenticated
 */
async function initAuthWithAdmin() {
    const user = await requireAuth();
    if (user) {
        updateUserUIWithAdmin(user);
    }
    return user;
}
