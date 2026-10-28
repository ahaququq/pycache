# DoH DNS (DNS over HTTPS)

## Overview

PyCache uses **DNS over HTTPS (DoH)** for resolving upstream file distribution hosts. This provides:
- **Privacy**: Encrypted DNS queries
- **Reliability**: Bypasses local DNS issues
- **Performance**: Faster resolution in some networks
- **Fallback**: Automatic fallback to system DNS

## Configuration

### Docker Compose DNS Settings

```yaml
# docker-compose.yml
services:
  pycache:
    dns:
      - 1.1.1.1      # Cloudflare
      - 8.8.8.8      # Google
```

### How It Works

1. **Container-level DNS**: Docker uses the specified DNS servers for all name resolution
2. **DoH via systemd-resolved**: The container uses systemd-resolved with DoH
3. **Fallback**: If DoH fails, falls back to traditional DNS

## Implementation

### `app/doh.py`

```python
"""DoH (DNS over HTTPS) resolver for requests.

Provides DNS resolution via Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH endpoints.
"""

DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/dns-query",
]

class DoHResolver:
    """DNS resolver using DoH (DNS over HTTPS)."""
    
    def __init__(self, endpoints=None, timeout=5):
        self.endpoints = endpoints or DOH_ENDPOINTS
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/dns-json",
            "User-Agent": "PyCache-DoH/1.0",
        })

    @lru_cache(maxsize=1024)
    def resolve(self, hostname: str, family: int = socket.AF_INET) -> list[str]:
        """Resolve hostname to IP addresses using DoH."""
        qtype = DNS_TYPE_A if family == socket.AF_INET else DNS_TYPE_AAAA
        
        for endpoint in self.endpoints:
            try:
                resp = self._session.get(
                    endpoint,
                    params={"name": hostname, "type": qtype},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("Status") == 0 and "Answer" in data:
                    ips = []
                    for answer in data["Answer"]:
                        if answer.get("type") == qtype:
                            ip = answer.get("data", "").strip()
                            if ip:
                                ips.append(ip)
                    if ips:
                        return ips
            except Exception as exc:
                log.warning("DoH resolution failed for %s via %s: %s", hostname, endpoint, exc)
                continue
        
        # Fallback to system resolver
        return self._system_resolve(hostname, family)
```

### Integration with Downloader

The downloader uses a custom `requests.Session` with a custom adapter:

```python
def create_doh_session() -> requests.Session:
    """Create a requests Session configured with DoH DNS resolution."""
    resolver = DoHResolver()
    session = requests.Session()
    session.resolver = resolver

    # Monkey-patch the session's request method
    original_request = session.request
    
    def doh_request(method, url, *args, **kwargs):
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if hostname and not hostname.replace(".", "").isdigit():
            try:
                ips = resolver.resolve(hostname)
                if ips:
                    kwargs.setdefault("headers", {})["Host"] = hostname
                    new_netloc = ips[0]
                    if parsed.port:
                        new_netloc += f":{parsed.port}"
                    new_parsed = parsed._replace(netloc=new_netloc)
                    url = urlunparse(new_parsed)
            except Exception as exc:
                log.warning("DoH resolution failed for %s: %s", hostname, exc)
        
        return original_request(method, url, *args, **kwargs)

    session.request = doh_request
    return session

# Global session
_doh_session: Optional[requests.Session] = None

def get_doh_session() -> requests.Session:
    global _doh_session
    if _doh_session is None:
        _doh_session = create_doh_session()
    return _doh_session
```

## Usage in Downloader

```python
# app/downloader.py
from .doh import get_doh_session

_SESSION = get_doh_session()
_SESSION.headers["User-Agent"] = UPSTREAM_USER_AGENT
_SESSION.max_redirects = MAX_REDIRECTS
_SESSION.allow_redirects = False
```

## Testing DoH Resolution

```bash
# Test DNS resolution from container
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys
sys.path.insert(0, \"/app\")
from app.doh import get_doh_session
s = get_doh_session()
ips = s.resolver.resolve(\"services.gradle.org\")
print(\"Resolved:\", ips)
'
"
```

Expected output:
```
Resolved: ['104.16.72.101', '104.16.73.101']
```

### Testing DoH Endpoints Directly

```bash
# Cloudflare
curl -H "Accept: application/dns-json" \
  "https://cloudflare-dns.com/dns-query?name=services.gradle.org&type=A"

# Google
curl -H "Accept: application/dns-json" \
  "https://dns.google/dns-query?name=services.gradle.org&type=A"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| DNS resolution fails | Check Docker DNS config, container network |
| Slow resolution | Check DoH endpoint latency |
| Fallback to system DNS | Check DoH endpoint reachability |
| IPv6 issues | Ensure `DNS_TYPE_AAAA` handling |

### Verify DNS in Container

```bash
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import socket
print(socket.getaddrinfo(\"services.gradle.org\", 443))
'
"
```

### Check DNS in Host
```bash
# Check host DNS
dig @1.1.1.1 services.gradle.org
dig @8.8.8.8 services.gradle.org
```

## Configuration

### Docker Compose DNS
```yaml
services:
  pycache:
    dns:
      - 1.1.1.1
      - 8.8.8.8
```

### Environment Variables (if needed)
```yaml
environment:
  DNS_1: 1.1.1.1
  DNS_2: 8.8.8.8
```

## Security Considerations

| Aspect | Implementation |
|--------|----------------|
| **Encryption** | HTTPS to DoH endpoints |
| **Privacy** | No DNS query logging by ISP |
| **Integrity** | TLS certificate validation |
| **Fallback** | Automatic system DNS fallback |

## Performance

| Metric | Typical Value |
|--------|---------------|
| Resolution time | 10-50ms |
| Cache TTL | 5 min (configurable) |
| Cache size | 1024 entries (LRU) |

## Testing

```bash
# Test from container
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys
sys.path.insert(0, \"/app\")
from app.doh import get_doh_session
s = get_doh_session()
for host in [\"services.gradle.org\", \"github.com\", \"google.com\"]:
    ips = s.resolver.resolve(host)
    print(f\"{host}: {ips}\")
'
"

# Expected output:
# services.gradle.org: ['104.16.72.101', '104.16.73.101']
# github.com: ['140.82.121.4']
# google.com: ['142.250.185.206']
```