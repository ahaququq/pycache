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

    // Confirm on delete/purge forms
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', e => {
            if (!confirm(form.getAttribute('data-confirm'))) e.preventDefault();
        });
    });

    // Notification system
    const notificationContainer = document.getElementById('notification-container');
    let activeDownloads = new Map();

    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function formatSpeed(bps) {
        return formatBytes(bps) + '/s';
    }

    function createDownloadNotification(path, totalBytes) {
        const notification = document.createElement('div');
        notification.className = 'download-notification downloading';
        notification.dataset.path = path;
        
        const filename = path.split('/').pop() || path;
        const sizeText = totalBytes ? ' (' + formatBytes(totalBytes) + ')' : '';
        
        notification.innerHTML = `
            <div class="notification-header">
                <span class="notification-title">Downloading</span>
                <span class="notification-filename" title="${path}">${filename}${sizeText}</span>
            </div>
            <div class="notification-progress-container">
                <div class="notification-progress-bar" style="width: 0%"></div>
            </div>
            <div class="notification-details">
                <span class="notification-progress-text">Starting...</span>
                <span class="notification-speed"></span>
            </div>
        `;
        
        notificationContainer.appendChild(notification);
        activeDownloads.set(path, notification);
        
        // Trigger reflow for animation
        notification.offsetHeight;
        notification.classList.add('show');
        
        return notification;
    }

    function updateDownloadNotification(path, downloaded, total, speed) {
        const notification = activeDownloads.get(path);
        if (!notification) return;
        
        const progressBar = notification.querySelector('.notification-progress-bar');
        const progressText = notification.querySelector('.notification-progress-text');
        const speedText = notification.querySelector('.notification-speed');
        
        if (total) {
            const percent = Math.min(100, (downloaded / total) * 100);
            progressBar.style.width = percent + '%';
            progressText.textContent = formatBytes(downloaded) + ' / ' + formatBytes(total) + ' (' + percent.toFixed(1) + '%)';
        } else {
            progressText.textContent = formatBytes(downloaded) + ' downloaded';
        }
        
        if (speed) {
            speedText.textContent = ' • ' + formatSpeed(speed);
        }
    }

    function completeDownloadNotification(path, success, errorMsg) {
        const notification = activeDownloads.get(path);
        if (!notification) return;
        
        notification.classList.remove('downloading');
        notification.classList.add(success ? 'completed' : 'failed');
        
        const progressBar = notification.querySelector('.notification-progress-bar');
        const progressText = notification.querySelector('.notification-progress-text');
        const speedText = notification.querySelector('.notification-speed');
        
        if (success) {
            progressBar.style.width = '100%';
            progressText.textContent = 'Download complete';
            speedText.textContent = '';
        } else {
            progressText.textContent = 'Failed: ' + (errorMsg || 'Unknown error');
            speedText.textContent = '';
        }
        
        // Remove after delay - stays until user dismisses or timeout
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
                activeDownloads.delete(path);
            }, 300);
        }, success ? 5000 : 10000);
    }

    function removeDownloadNotification(path) {
        const notification = activeDownloads.get(path);
        if (!notification) return;
        
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();
            activeDownloads.delete(path);
        }, 300);
    }

    // Expose for use in other scripts
    window.downloadNotifications = {
        start: createDownloadNotification,
        update: updateDownloadNotification,
        complete: completeDownloadNotification,
        remove: removeDownloadNotification
    };

    // Download and probe buttons
    document.querySelectorAll('button[data-action="download"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const path = btn.getAttribute('data-path');
            const url = btn.getAttribute('data-url') || '/api/download';
            
            // Add loading state to button
            btn.disabled = true;
            btn.dataset.originalText = btn.textContent;
            btn.innerHTML = '<span class="spinner"></span> Downloading...';
            
            // Create notification - will stay until download completes
            const notification = createDownloadNotification(path);
            
            fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({local_path: path})
            }).then(r => r.json()).then(d => {
                if (d.ok) {
                    completeDownloadNotification(path, true);
                    // Reload page after a short delay to update the table
                    setTimeout(() => location.reload(), 1500);
                } else {
                    completeDownloadNotification(path, false, d.error);
                }
                // Restore button
                btn.disabled = false;
                btn.textContent = btn.dataset.originalText || 'Download';
            }).catch(err => {
                completeDownloadNotification(path, false, err.message);
                btn.disabled = false;
                btn.textContent = btn.dataset.originalText || 'Download';
            });
        });
    });

    document.querySelectorAll('button[data-action="probe"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const path = btn.getAttribute('data-path');
            const url = btn.getAttribute('data-url') || '/api/probe';
            fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({local_path: path})
            }).then(r => r.json()).then(d => {
                let msg = 'Status: ' + d.status + '\n';
                msg += 'Exists: ' + d.exists + '\n';
                msg += 'Size: ' + (d.size ? d.size + ' bytes' : 'unknown') + '\n';
                msg += 'Final URL: ' + d.final_url;
                if (d.error) msg += '\nError: ' + d.error;
                // Don't use alert, the modal will show the result
            });
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