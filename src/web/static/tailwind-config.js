/**
 * Shared Tailwind CSS configuration for all pages
 * Include this script after the Tailwind CDN script
 */
if (typeof tailwind !== 'undefined') {
    tailwind.config = {
        theme: {
            extend: {
                colors: {
                    primary: '#2563eb',
                    secondary: '#64748b',
                }
            }
        }
    };
}
