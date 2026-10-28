# Unavailable File Handling

## Overview

PyCache handles files that are listed in a source index but are **not actually available** upstream (e.g., HTTP 404, 403, 410). These files are tagged as "Unavailable" with an error reason.

## How It Works

### Detection

Files become "unavailable" when:
1. **Probe** (`/api/probe` or `/probe/<path>`) returns non-200 status
2. **Download** fails with 4xx/5xx status
3. **Manual marking** via database

### Database Schema

```sql
-- files table additions
unavailable INTEGER NOT NULL DEFAULT 0,     -- 1 = unavailable
unavailable_reason TEXT,                     -- e.g., "upstream returned 404"
exists_upstream INTEGER NOT NULL DEFAULT 0,  -- 1 = HEAD succeeded
```

### Tagging Logic

```python
# In probe endpoint (app/routes/public.py)
if result.ok:
    # File exists upstream
    db.execute("""... ON CONFLICT DO UPDATE SET
        exists_upstream=1, unavailable=0, unavailable_reason=NULL...""")
else:
    # File unavailable upstream
    error_reason = result.error or f"HTTP {result.status}"
    db.execute("""... ON CONFLICT DO UPDATE SET
        exists_upstream=0, unavailable=1, unavailable_reason=?, ...""",
        (error_reason, error_reason))
```

## UI Indicators

### Badge Display

| Status | Badge Class | Color | Tooltip |
|--------|-------------|-------|---------|
| Cached | `badge-cached` | Green | "Cached" |
| Upstream | `badge-upstream` | Blue | "Upstream" |
| Missing | `badge-missing` | Gray | "Missing" |
| **Unavailable** | `badge-unavailable` | **Red** | **Error reason on hover** |

### Template Logic (by_path.html)

```jinja
{% if r.unavailable %}
    {% set cls = 'unavailable' %}
    {% set status_badge = '<span class="badge badge-unavailable" title="' ~ 
        (r.unavailable_reason or 'Unavailable') ~ '">Unavailable</span>' %}
{% elif r.cached %}
    {% set cls = 'cached' %}
    {% set status_badge = '<span class="badge badge-cached">Cached</span>' %}
{% elif r.exists_upstream %}
    {% set cls = 'upstream-only' %}
    {% set status_badge = '<span class="badge badge-upstream">Upstream</span>' %}
{% else %}
    {% set cls = 'missing' %}
    {% set status_badge = '<span class="badge badge-missing">Missing</span>' %}
{% endif %}
```

### CSS Styling

```css
/* Unavailable badge */
.badge-unavailable { 
    background: rgba(220, 38, 38, 0.2); 
    color: var(--error); 
}

tr.unavailable .badge-unavailable { display: inline-block; }

/* Disabled button for unavailable */
.btn-disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background: var(--card);
    color: var(--muted);
    border-color: var(--border);
}
```

## UI Behavior

| Status | Download Button | Probe Button | Serve Link |
|--------|----------------|--------------|------------|
| Cached | ❌ Hidden | ✅ Probe | ✅ Serve link |
| Upstream | ✅ Download | ✅ Probe | ❌ |
| Unavailable | ❌ Hidden | ✅ Probe | ❌ |
| Missing | ✅ Download | ✅ Probe | ❌ |

## Probe Functionality

### Probe Endpoint
```
POST /api/probe
Content-Type: application/json
{"local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip"}
```

### Probe Response

**Available:**
```json
{
  "ok": true,
  "local_path": "gradle/8.5/gradle-8.5-bin.zip",
  "status": 200,
  "exists": true,
  "size": 132519731,
  "error": null,
  "unavailable_reason": null
}
```

**Unavailable:**
```json
{
  "ok": true,
  "exists": false,
  "status": 404,
  "error": "upstream returned 404",
  "unavailable_reason": "upstream returned 404",
  "size": 29,
  "final_url": "https://github.com/..."
}
```

### Probe Button Behavior

- **Available**: Shows "Upstream" badge, Probe works
- **Unavailable**: Shows "Unavailable" badge, Probe shows error details
- **Missing**: Shows "Missing" badge, Probe triggers fresh check

## Probe Modal (HTML-based)

### Features
- **No `alert()`** - Uses modal dialog
- **Table format** with all probe details
- **Close**: X button, backdrop click, Escape key
- **Mobile-friendly** responsive design

### JavaScript Implementation

```javascript
function openProbeModal(path) {
    fetch('/api/probe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({local_path: path})
    }).then(r => r.json()).then(d => {
        // Build table
        const fields = [
            ['Local Path', d.local_path],
            ['Remote URL', d.remote_url],
            ['Final URL', d.final_url],
            ['Status', d.status + (d.exists ? ' ✓' : ' ✗')],
            ['Exists', d.exists ? 'Yes' : 'No'],
            ['Size', d.size ? d.size + ' bytes' : 'Unknown'],
            ['Content Type', d.content_type || 'Unknown'],
            ['ETag', d.etag || 'N/A'],
            ['Last Modified', d.last_modified || 'N/A'],
            ['Error', d.error || 'None'],
            ['Unavailable Reason', d.unavailable_reason || 'N/A']
        ];
        
        let html = '<table style="width:100%; border-collapse: collapse;">';
        html += '<tr><th style="text-align:left; padding: 0.5rem;">Property</th><th style="text-align:left; padding: 0.5rem;">Value</th></tr>';
        
        fields.forEach(([key, value]) => {
            html += `<tr><td style="padding: 0.5rem; font-weight: bold; border-bottom: 1px solid var(--border);">${key}</td>`;
            html += `<td style="padding: 0.5rem; border-bottom: 1px solid var(--border); font-family: monospace; word-break: break-all;">${value || '—'}</td></tr>`;
        });
        
        html += '</table>';
        document.getElementById('probe-modal-body').innerHTML = html;
        document.getElementById('probe-modal').style.display = 'flex';
    });
}

function closeProbeModal() {
    document.getElementById('probe-modal').style.display = 'none';
}

// Close on X button
document.getElementById('probe-modal-close').addEventListener('click', closeProbeModal);

// Close on backdrop click
document.getElementById('probe-modal').addEventListener('click', function(e) {
    if (e.target === this) closeProbeModal();
});

// Close on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeProbeModal();
});
```

## CSS for Modal

```css
.modal {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    z-index: 10001;
    display: flex; align-items: center; justify-content: center;
    padding: 1rem;
}

.modal-backdrop {
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.5); backdrop-filter: blur(2px);
}

.modal-content {
    position: relative; background: var(--card);
    border: 1px solid var(--border); border-radius: 8px;
    box-shadow: var(--shadow); max-width: 90vw; max-height: 90vh;
    width: 600px; display: flex; flex-direction: column;
    overflow: hidden; animation: modalSlideIn 0.2s ease;
}

.modal-close {
    background: none; border: none; font-size: 1.5rem;
    cursor: pointer; color: var(--muted); padding: 0; line-height: 1;
}
.modal-close:hover { color: var(--fg); }

.modal-body { padding: 1rem; overflow-y: auto; max-height: 70vh; }
.modal-body table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.modal-body th { font-weight: 600; color: var(--muted); width: 30%; white-space: nowrap; }
.modal-body td { font-family: ui-monospace, monospace; font-size: 0.8rem; word-break: break-all; }
```

## Testing Unavailable Files

### Probe Unavailable File
```bash
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip"}'
```

### Expected Response
```json
{
  "content_type": "text/plain; charset=utf-8",
  "error": "upstream returned 404",
  "etag": null,
  "exists": false,
  "final_url": "https://github.com/gradle/gradle-distributions/releases/download/v1.0.0-M2a/gradle-1.0-milestone-2a-bin.zip",
  "last_modified": null,
  "local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip",
  "ok": true,
  "remote_url": "https://services.gradle.org/distributions/gradle-1.0-milestone-2a-bin.zip",
  "size": 29,
  "source_id": 1,
  "status": 404,
  "unavailable_reason": "upstream returned 404"
}
```

### Verify in Database

```bash
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sqlite3
conn = sqlite3.connect(\"/app/app/data/cache_server.db\")
rows = conn.execute(\"SELECT local_path, exists_upstream, unavailable, unavailable_reason FROM files WHERE local_path LIKE \\\"gradle/1.0-milestone-2a%\\\"\").fetchall()
for r in rows:
    print(dict(zip([\"local_path\", \"exists_upstream\", \"unavailable\", \"unavailable_reason\"], r)))
'
"
```

Expected:
```json
{
  "local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip",
  "exists_upstream": 0,
  "unavailable": 1,
  "unavailable_reason": "upstream returned 404"
}
```

### Template Rendering

The unavailable file shows:
- **Badge**: Red "Unavailable" with tooltip "upstream returned 404"
- **Disabled download**: Greyed out "Unavailable" text
- **Probe button**: Works to re-check
- **Status column**: Shows "Unavailable" badge

## Summary

| Feature | Implementation |
|--------|----------------|
| **Detection** | Probe/download 4xx/5xx |
| **Database** | `unavailable`, `unavailable_reason` columns |
| **UI Badge** | Red "Unavailable" with hover tooltip |
| **Download** | Disabled for unavailable files |
| **Probe** | Shows detailed error in modal |
| **Database** | `unavailable=1`, `unavailable_reason="upstream returned 404"` |