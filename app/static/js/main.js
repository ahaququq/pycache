// Utilitarian JS - minimal, no frameworks

(function() {
    // Theme toggle
    const btn = document.getElementById('theme-toggle');
    const root = document.documentElement;
    const themes = ['light', 'dark', 'auto'];
    let current = localStorage.getItem('theme') || 'auto';

    function applyTheme(t) {
        let effective = t;
        if (t === 'auto') {
            effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        root.setAttribute('data-theme', effective);
        localStorage.setItem('theme', t);
        updateIcon();
    }

    function updateIcon() {
        if (!btn) return;
        const t = localStorage.getItem('theme') || 'auto';
        btn.textContent = t === 'dark' ? '☀️' : t === 'light' ? '🌙' : '🌓';
        btn.title = 'Theme: ' + t;
    }

    if (btn) {
        btn.addEventListener('click', () => {
            const idx = themes.indexOf(current);
            current = themes[(idx + 1) % themes.length];
            applyTheme(current);
        });
        updateIcon();
        // Listen for system theme changes when in auto
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
            if (current === 'auto') applyTheme('auto');
        });
    }

    // Flash message auto-dismiss
    document.querySelectorAll('.flash').forEach(el => {
        setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .5s'; setTimeout(() => el.remove(), 500); }, 5000);
    });

    // Confirm on delete buttons
    document.querySelectorAll('form[action*="/delete"]').forEach(form => {
        form.addEventListener('submit', e => {
            if (!confirm('Are you sure?')) e.preventDefault();
        });
    });

    // Copy to clipboard helper
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            const toast = document.createElement('div');
            toast.textContent = 'Copied!';
            toast.style.cssText = 'position:fixed;bottom:1rem;right:1rem;padding:.5rem 1rem;background:var(--accent);color:#fff;border-radius:4px;z-index:9999';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        });
    };
})();