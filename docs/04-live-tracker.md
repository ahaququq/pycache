# Live Tracker

The Live Tracker provides real-time visibility into download, serve, and probe activities through a Server-Sent Events (SSE) stream.

## Access

**URL**: `http://localhost:80/admin/tracker`

## Features

### Real-time Updates
- **Server-Sent Events (SSE)** stream at `/api/tracker/stream`
- Real-time updates without polling
- Auto-reconnect on disconnect

### Stats Panel
| Metric | Description |
|--------|-------------|
| Active Downloads | Currently downloading files |
| Active Serves | Files being served from cache |
| Total Events | Total events this session |
| Errors | Count of download/serve errors |

### Progress Bars
- **Max 5 visible** (configurable via `MAX_PROGRESS_BARS`)
- **Scrollable** for additional entries
- **Color coding**:
  - 🔵 Blue = Active (downloading/serving)
  - ✅ Green = Complete
  - 🔴 Red = Error
- **Details shown**:
  - File path
  - Percentage complete
  - Bytes transferred / total
  - Speed (MB/s)
  - Duration
  - Source (cache/upstream)

### Event Log
- **Filterable** by event type and text search
- **Columns**: Time, Type, Message
- **Click** event → View details (JSON modal)
- **Clear View** button resets filters
- **Auto-load** on page load (200 events)

## Event Types

### Download Events
| Event | Description |
|-------|-------------|
| `download_start` | Download initiated |
| `download_redirect` | Redirect encountered |
| `download_progress` | Progress update with %/speed |
| `download_complete` | Download finished |
| `download_error` | Download failed |

### Serve Events
| Event | Description |
|-------|-------------|
| `serve_start` | Serve initiated |
| `serve_complete` | File served successfully |
| `serve_error` | Serve failed |

### Probe Events
| Event | Description |
|-------|-------------|
| `probe_start` | Probe initiated |
| `probe_complete` | Probe finished |

## Event Details Modal

Click any event row to view full details:
```json
{
  "id": 42,
  "timestamp": "2026-10-27 15:45:27",
  "event_type": "download_progress",
  "message": "Downloading gradle/8.5/gradle-8.5-bin.zip: 73,531,392 / 132,519,731 bytes (55.5%) @ 110.71 MB/s",
  "details": {
    "local_path": "gradle/8.5/gradle-8.5-bin.zip",
    "bytes_downloaded": 73531392,
    "total_bytes": 132519731,
    "progress_pct": 55.49,
    "speed_bps": 116089658,
    "speed_mbps": 110.71,
    "source_name": "gradle_dist"
  }
}
```

## API Endpoints

### SSE Stream
```
GET /api/tracker/stream
```
- **Format**: Server-Sent Events
- **Heartbeat**: `data: : heartbeat\n\n` every 5 seconds
- **Auto-reconnect**: Browser handles reconnection

### Event List
```
GET /api/tracker/events?limit=200&type=download
```
- **Query params**:
  - `limit`: Max events (default 100)
  - `type`: Filter by event type (comma-separated)

### Statistics
```
GET /api/tracker/stats
```
Returns:
```json
{
  "download_start": 10,
  "download_progress": 5,
  "download_complete": 8,
  "download_error": 0,
  "serve_start": 5,
  "serve_complete": 4,
  "serve_error": 0,
  "probe_start": 3,
  "probe_complete": 3
}
```

### Event List
```
GET /api/tracker/events?limit=200&type=download_complete
```
Returns array of event objects:
```json
{
  "id": 42,
  "timestamp": "2026-10-27 15:45:27",
  "event_type": "download_complete",
  "message": "Downloaded gradle/8.5/gradle-8.5-bin.zip (132,519,731 bytes in 1.5s, 82.42 MB/s) → cached",
  "details": {
    "local_path": "gradle/8.5/gradle-8.5-bin.zip",
    "bytes_downloaded": 132519731,
    "duration_s": 1.53,
    "speed_mbps": 82.42,
    "cache_path": "/app/app/cache/...",
    "source_name": "gradle_dist"
  }
}
```

## Frontend Implementation

### SSE Connection
```javascript
const eventSource = new EventSource('/api/tracker/stream');

eventSource.onopen = () => updateStatus(true);
eventSource.onerror = () => {
  updateStatus(false);
  setTimeout(() => { eventSource.close(); connectSSE(); }, 3000);
};

eventSource.onmessage = (e) => {
  if (e.data.startsWith(':')) return; // Heartbeat
  const event = JSON.parse(e.data);
  // Process event...
};
```

### Progress Bar Management
```javascript
const progressBars = new Map(); // path -> DOM element
const MAX_PROGRESS_BARS = 5;

function addOrUpdateProgressBar(event) {
  const path = event.details.local_path;
  let item = progressBars.get(path);
  
  if (!item) {
    // Create new
    item = createProgressBar(event);
    progressBars.set(path, item);
    progressOrder.push(path);
    container.insertBefore(item, container.firstChild);
    
    // Limit to MAX_PROGRESS_BARS
    while (progressOrder.length > MAX_PROGRESS_BARS) {
      const oldPath = progressOrder.shift();
      progressBars.get(oldPath)?.remove();
      progressBars.delete(oldPath);
    }
  } else {
    updateProgressBar(item, event);
  }
  
  // Auto-remove completed/error after 5s
  if (isTerminalEvent) {
    setTimeout(() => removeProgressBar(path), 5000);
  }
}
```

### Event Log with Filters
```javascript
function addEventToLog(event) {
  // Apply filters
  if (filterType && event.event_type !== filterType) return;
  if (filterText && !event.message.toLowerCase().includes(filterText)) return;
  
  const line = document.createElement('div');
  line.className = 'event-line';
  line.innerHTML = `
    <span class="event-time">${time}</span>
    <span class="event-type type-${event.event_type}">${event.event_type}</span>
    <span class="event-message">${event.message}</span>
  `;
  container.insertBefore(line, container.firstChild);
}
```

## API Endpoints Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tracker/stream` | GET | SSE stream |
| `/api/tracker/events` | GET | Recent events (JSON) |
| `/api/tracker/stats` | GET | Event counts by type |
| `/api/tracker/stream` | GET | SSE stream |

### Query Parameters

| Endpoint | Params |
|----------|--------|
| `/api/tracker/events` | `limit` (default 100), `type` (comma-separated) |
| `/api/tracker/stats` | none |

## Event Type Reference

| Type | Category | Description |
|------|----------|-------------|
| `download_start` | Download | Download initiated |
| `download_redirect` | Download | Redirect encountered |
| `download_progress` | Download | Progress update |
| `download_complete` | Download | Success |
| `download_error` | Download | Failed |
| `serve_start` | Serve | Serve initiated |
| `serve_complete` | Serve | Served successfully |
| `serve_error` | Serve | Serve failed |
| `probe_start` | Probe | Probe initiated |
| `probe_complete` | Probe | Probe finished |

## Connection Management

- **Auto-reconnect**: 3 seconds after disconnect
- **Heartbeat**: `data: : heartbeat\n\n` every 5 seconds
- **Max events**: 500 in memory (configurable)
- **Reconnect delay**: 3 seconds

## Stats Calculation

```javascript
// Active = started - completed
const activeDownloads = stats.download_start - stats.download_complete;
const activeServes = stats.serve_start + stats.serve_complete; // approx
const totalEvents = eventCount;
const errors = stats.download_error + stats.serve_error;
```

## Connection Status Indicator

```html
<div class="connection-status">
  <span class="status-dot"></span>
  <span id="status-text">Connecting...</span>
</div>

<script>
function updateStatus(connected) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (connected) {
    dot.classList.remove('disconnected', 'connecting');
    text.textContent = 'Connected';
  } else {
    dot.classList.add('disconnected');
    text.textContent = 'Disconnected';
  }
}
</script>
```

## CSS Classes for Progress Bars

```css
.progress-bar-fill {
  transition: width 0.3s ease;
  background: linear-gradient(90deg, var(--accent), #3b82f6);
}
.progress-bar-fill.complete { background: linear-gradient(90deg, #22c55e, #16a34a); }
.progress-bar-fill.error { background: linear-gradient(90deg, #ef4444, #dc2626); }
```

## Browser Compatibility

- **Firefox**: Fully tested ✅
- **Chromium/Chrome**: ✅
- **Safari**: SSE supported (partial)
- **Edge**: ✅
- **IE**: Not supported (no SSE)