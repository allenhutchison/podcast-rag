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

    // Create container div
    const container = document.createElement('div');
    container.className = 'flex items-center gap-3';

    // Create and configure image element
    const validPictureUrl = validatePictureUrl(user.picture);
    if (validPictureUrl) {
        const img = document.createElement('img');
        img.src = validPictureUrl;
        img.alt = user.name || user.email || 'User';
        img.className = 'w-8 h-8 rounded-full';
        img.referrerPolicy = 'no-referrer';
        img.addEventListener('error', function() {
            this.style.display = 'none';
        });
        container.appendChild(img);
    }

    // Create name/email span
    const nameSpan = document.createElement('span');
    nameSpan.className = 'text-gray-700 text-sm hidden sm:inline';
    nameSpan.textContent = user.name || user.email || '';
    container.appendChild(nameSpan);

    // Add admin link for admin users (if enabled)
    if (showAdminLink && isAdmin(user)) {
        const adminLink = document.createElement('a');
        adminLink.href = '/admin.html';
        adminLink.className = 'text-primary hover:text-blue-700 text-sm font-medium';
        adminLink.textContent = 'Admin';
        container.appendChild(adminLink);
    }

    // Create logout button
    const logoutBtn = document.createElement('button');
    logoutBtn.className = 'text-gray-500 hover:text-gray-700 text-sm underline';
    logoutBtn.textContent = 'Sign out';
    logoutBtn.addEventListener('click', logout);
    container.appendChild(logoutBtn);

    userInfoContainer.appendChild(container);
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
