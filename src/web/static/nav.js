/**
 * Shared navigation header component for all pages.
 * Renders a consistent header with nav tabs and user info.
 *
 * Usage: Add <div id="app-header"></div> and <script src="/nav.js"></script>
 * Optionally set data-active attribute on the div: data-active="feed|subscriptions|chat|settings|admin"
 * Optionally set data-title for a page-specific title shown on mobile instead of nav tabs.
 */
(function () {
    const NAV_ITEMS = [
        { id: 'feed', label: 'Feed', href: '/feed.html' },
        { id: 'subscriptions', label: 'Subscriptions', href: '/podcasts.html' },
        { id: 'chat', label: 'Chat', href: '/chat.html' },
        { id: 'settings', label: 'Settings', href: '/settings.html' },
    ];

    function renderNav() {
        const container = document.getElementById('app-header');
        if (!container) return;

        const active = container.dataset.active || '';
        const pageTitle = container.dataset.title || '';

        const navLinks = NAV_ITEMS.map(item => {
            if (item.id === active) {
                return `<span class="px-3 py-1.5 bg-primary text-white rounded-lg font-medium text-sm">${item.label}</span>`;
            }
            return `<a href="${item.href}" class="px-3 py-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg text-sm">${item.label}</a>`;
        }).join('');

        // On mobile: show page title or active tab name; on desktop: show full nav
        const mobileLabel = pageTitle || NAV_ITEMS.find(i => i.id === active)?.label || '';

        container.innerHTML = `
            <header class="bg-white border-b border-gray-200 px-4 sm:px-6 py-3 shadow-sm">
                <div class="max-w-6xl mx-auto flex justify-between items-center">
                    <nav class="flex items-center gap-1">
                        <span class="sm:hidden text-lg font-bold text-gray-900">${mobileLabel}</span>
                        <div class="hidden sm:flex items-center gap-1">
                            ${navLinks}
                        </div>
                    </nav>
                    <div class="flex items-center gap-2 sm:gap-4">
                        <div id="userInfo" class="border-l pl-2 sm:pl-4 border-gray-200"></div>
                    </div>
                </div>
            </header>
        `;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderNav);
    } else {
        renderNav();
    }
})();
