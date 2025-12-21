/**
 * Shared footer component for all pages
 * Automatically renders the footer on page load
 */
(function() {
    const footerHTML = `
        <footer class="bg-white border-t border-gray-200 px-6 py-4">
            <div class="max-w-6xl mx-auto text-center text-sm text-gray-600">
                <div class="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-4 flex-wrap">
                    <span class="w-full sm:w-auto">Brought to you by Allen Hutchison</span>
                    <div class="flex items-center gap-4 flex-wrap justify-center">
                        <a href="https://github.com/allenhutchison/podcast-rag" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-700 hover:underline">
                            GitHub
                        </a>
                        <span class="text-gray-300">•</span>
                        <a href="https://allen.hutchison.org/" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-700 hover:underline">
                            Blog
                        </a>
                        <span class="text-gray-300">•</span>
                        <a href="https://x.com/allen_hutchison" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-700 hover:underline">
                            X
                        </a>
                        <span class="text-gray-300">•</span>
                        <a href="https://bsky.app/profile/allen.hutchison.org" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-700 hover:underline">
                            Bluesky
                        </a>
                        <span class="text-gray-300">•</span>
                        <a href="https://www.linkedin.com/in/allenhutchison/" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-700 hover:underline">
                            LinkedIn
                        </a>
                    </div>
                </div>
            </div>
        </footer>
    `;

    // Render footer when DOM is ready
    function renderFooter() {
        const footerContainer = document.getElementById('app-footer');
        if (footerContainer) {
            footerContainer.innerHTML = footerHTML;
        }
    }

    // Run immediately if DOM is already loaded, otherwise wait
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderFooter);
    } else {
        renderFooter();
    }
})();
