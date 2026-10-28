# System-Wide Gradle Setup Guide

## Overview

This guide explains how to configure **gradlew (Gradle Wrapper)** system-wide to download **all Gradle distributions** through your PyCache cache server. This is useful for:
- Teams sharing a single PyCache instance
- CI/CD environments needing fast, reliable Gradle downloads
- Offline/air-gapped environments with pre-populated cache
- Centralized control over Gradle versions

---

## Prerequisites

- PyCache running and accessible (e.g., `http://pycache.local:80` or `http://localhost:80`)
- Gradle source configured in PyCache Admin Panel (enabled by default)
- Access to modify user-level or system-level Gradle configuration

---

## Method 1: GRADLE_USER_HOME Environment Variable (Recommended)

This is the **simplest and most portable** method. Set the `GRADLE_USER_HOME` environment variable to point to a shared directory that uses PyCache.

### How It Works

Gradle uses `GRADLE_USER_HOME` for:
- Wrapper distributions cache (`wrapper/dists/`)
- Global Gradle caches
- Configuration files

By setting this to a location served by PyCache, all Gradle wrapper downloads go through PyCache automatically.

### Linux/macOS (Per User)

Add to `~/.bashrc`, `~/.zshrc`, or `~/.profile`:

```bash
# PyCache Gradle cache
export GRADLE_USER_HOME="${HOME}/.gradle-pycache"
```

Then create a `gradle.properties` in that directory:

```bash
mkdir -p "${HOME}/.gradle-pycache"
cat > "${HOME}/.gradle-pycache/gradle.properties" << 'EOF'
# PyCache Gradle Distribution Cache
# This makes ALL gradlew invocations use PyCache for wrapper downloads

# The key setting: use PyCache for distribution downloads
# Format: http://<pycache-host>/cache/gradle/<version>/gradle-<version>-bin.zip
# The actual distributionUrl is set per-project in gradle/wrapper/gradle-wrapper.properties
# But we can override the base URL pattern via init script (see Method 2)

# Optional: Disable Gradle's own checksum validation (PyCache handles this)
# systemProp.gradle.wrapper.validateDistributionUrl=false
EOF
```

### Linux/macOS (System-Wide)

Create `/etc/profile.d/pycache-gradle.sh`:

```bash
sudo tee /etc/profile.d/pycache-gradle.sh > /dev/null << 'EOF'
# PyCache system-wide Gradle configuration
export GRADLE_USER_HOME="/var/cache/gradle-pycache"
EOF

sudo mkdir -p /var/cache/gradle-pycache
sudo chmod 777 /var/cache/gradle-pycache
```

### Windows (Per User)

```powershell
# PowerShell (run as user)
[Environment]::SetEnvironmentVariable("GRADLE_USER_HOME", "$env:USERPROFILE\.gradle-pycache", "User")
```

Create `%USERPROFILE%\.gradle-pycache\gradle.properties`:

```properties
# PyCache Gradle Distribution Cache
```

### Windows (System-Wide)

```powershell
# PowerShell (run as Administrator)
[Environment]::SetEnvironmentVariable("GRADLE_USER_HOME", "C:\gradle-pycache", "Machine")
```

---

## Method 2: Gradle Init Script (Most Powerful)

This method uses a **Gradle init script** to automatically rewrite **any** `distributionUrl` to point to PyCache, regardless of what the project's `gradle-wrapper.properties` says.

### Create Init Script

**Linux/macOS:** `~/.gradle/init.d/pycache-distributions.gradle`

**Windows:** `%USERPROFILE%\.gradle\init.d\pycache-distributions.gradle`

**System-wide (Linux):** `/etc/gradle/init.d/pycache-distributions.gradle`

```groovy
// pycache-distributions.gradle
// Automatically redirects ALL Gradle wrapper downloads to PyCache

import org.gradle.api.invocation.Gradle
import org.gradle.wrapper.GradleWrapperMain

allprojects {
    // This runs for every Gradle build
    gradle.projectsLoaded {
        // Override the wrapper task to use PyCache
        tasks.withType(Wrapper) {
            // Only modify if not already pointing to PyCache
            if (distributionUrl && !distributionUrl.toString().contains("pycache") && !distributionUrl.toString().contains("localhost")) {
                def originalUrl = distributionUrl.toString()
                // Extract version from URL like:
                // https://services.gradle.org/distributions/gradle-8.5-bin.zip
                // https://downloads.gradle-dn.com/distributions/gradle-8.5-bin.zip
                def versionMatcher = originalUrl =~ /gradle-([\d.]+)(?:-(?:all|bin))?\.zip/
                if (versionMatcher.matches()) {
                    def version = versionMatcher[0][1]
                    def pycacheUrl = "http://pycache.local:80/cache/gradle/${version}/gradle-${version}-bin.zip"
                    println "PyCache: Rewriting Gradle wrapper distributionUrl"
                    println "  From: ${originalUrl}"
                    println "  To:   ${pycacheUrl}"
                    distributionUrl = pycacheUrl
                }
            }
        }
    }
}

// Alternative: Intercept the wrapper download directly
// This works even without the Wrapper task
settingsEvaluated { settings ->
    // Configure the Gradle distribution download location
    def pycacheBase = "http://pycache.local:80/cache/gradle"
    
    // Hook into the distribution download mechanism
    def wrapperTask = settings.gradle.rootProject.tasks.findByName("wrapper")
    if (wrapperTask != null) {
        wrapperTask.doLast {
            def wrapperProps = new File(settings.gradle.rootProject.projectDir, "gradle/wrapper/gradle-wrapper.properties")
            if (wrapperProps.exists()) {
                def props = new Properties()
                wrapperProps.withInputStream { props.load(it) }
                def currentUrl = props.getProperty("distributionUrl")
                if (currentUrl && !currentUrl.contains("pycache") && !currentUrl.contains("localhost")) {
                    def versionMatcher = currentUrl =~ /gradle-([\d.]+)(?:-(?:all|bin))?\.zip/
                    if (versionMatcher.matches()) {
                        def version = versionMatcher[0][1]
                        def newUrl = "${pycacheBase}/${version}/gradle-${version}-bin.zip"
                        props.setProperty("distributionUrl", newUrl)
                        wrapperProps.withOutputStream { props.store(it, "Updated by PyCache init script") }
                        println "PyCache: Updated wrapper distributionUrl to ${newUrl}"
                    }
                }
            }
        }
    }
}
```

### Simpler Init Script (Just URL Rewrite)

If you want a simpler version that just rewrites URLs at the source:

```groovy
// ~/.gradle/init.d/pycache-distributions.gradle (simple version)

gradle.projectsLoaded {
    tasks.withType(Wrapper) { task ->
        def originalUrl = task.distributionUrl?.toString()
        if (originalUrl && (originalUrl.contains("services.gradle.org") || originalUrl.contains("downloads.gradle"))) {
            // Extract version: gradle-8.5-bin.zip -> 8.5
            def version = (originalUrl =~ /gradle-([\d.]+)-/).find() ? (originalUrl =~ /gradle-([\d.]+)-/).find()[0][1] : null
            if (version) {
                def pycacheUrl = "http://pycache.local:80/cache/gradle/${version}/gradle-${version}-bin.zip"
                task.distributionUrl = pycacheUrl
                logger.lifecycle("PyCache: Rewriting Gradle distribution URL")
                logger.lifecycle("  From: ${originalUrl}")
                logger.lifecycle("  To:   ${pycacheUrl}")
            }
        }
    }
}
```

---

## Method 3: Per-Project gradle-wrapper.properties (Standard)

This is the standard method documented in [09-gradle-integration.md](./09-gradle-integration.md). Each project configures its own wrapper.

### Project Configuration

Edit `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
# Point to PyCache instead of services.gradle.org
distributionUrl=http://pycache.local:80/cache/gradle/8.10/gradle-8.10-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

### Update Wrapper

```bash
# Regenerate wrapper scripts with new URL
./gradlew wrapper
```

---

## Method 4: Docker/CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/build.yml
name: Build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      GRADLE_USER_HOME: ${{ runner.temp }}/gradle-cache
      GRADLE_OPTS: "-Dgradle.user.home=${{ runner.temp }}/gradle-cache"
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up PyCache Gradle
        run: |
          mkdir -p "${GRADLE_USER_HOME}"
          cat > "${GRADLE_USER_HOME}/gradle.properties" << 'EOF'
          # PyCache for GitHub Actions
          systemProp.gradle.wrapper.validateDistributionUrl=false
          EOF
      
      - name: Build with Gradle
        run: ./gradlew build
        env:
          # Point wrapper downloads to PyCache
          GRADLE_OPTS: "-Dgradle.user.home=${{ runner.temp }}/gradle-cache"
```

### GitLab CI

```yaml
# .gitlab-ci.yml
variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle-pycache"
  GRADLE_OPTS: "-Dgradle.user.home=$CI_PROJECT_DIR/.gradle-pycache"

before_script:
  - mkdir -p "$GRADLE_USER_HOME"
  - |
    cat > "$GRADLE_USER_HOME/gradle.properties" << 'EOF'
    # PyCache for GitLab CI
    systemProp.gradle.wrapper.validateDistributionUrl=false
    EOF

build:
  script:
    - ./gradlew build
```

### Dockerfile

```dockerfile
# Dockerfile
FROM gradle:8.10-jdk21 AS builder

# Configure PyCache
ENV GRADLE_USER_HOME=/home/gradle/.gradle-pycache
ENV GRADLE_OPTS="-Dgradle.user.home=/home/gradle/.gradle-pycache"

# Create init script for automatic URL rewriting
RUN mkdir -p /home/gradle/.gradle/init.d
COPY pycache-distributions.gradle /home/gradle/.gradle/init.d/

WORKDIR /home/gradle/project
COPY --chown=gradle:gradle . .
RUN gradle build --no-daemon
```

---

## Method 5: Network-Level (Transparent Proxy)

For **zero-configuration** deployments, use a transparent proxy or DNS override.

### /etc/hosts Override (Quick Test)

```bash
# On each machine
echo "192.168.1.100  services.gradle.org downloads.gradle.org" | sudo tee -a /etc/hosts
```

Then ensure PyCache serves on port 80/443 with proper SSL.

### Nginx Reverse Proxy (Production)

On your PyCache host, add to nginx config:

```nginx
# /etc/nginx/conf.d/gradle-cache.conf
server {
    listen 80;
    server_name services.gradle.org downloads.gradle.org;
    
    location /distributions/ {
        proxy_pass http://localhost:80/cache/gradle/;
        proxy_set_header Host $host;
        proxy_cache_valid 200 1y;
    }
}
```

This makes **any** Gradle download transparent - no configuration changes needed!

---

## Verification

### Test Wrapper Download

```bash
# First run - should download via PyCache
./gradlew --version

# Check PyCache tracker
curl http://pycache.local/admin/tracker

# Check cache
ls -la ~/.gradle-pycache/wrapper/dists/
# or
ls -la /var/cache/gradle-pycache/wrapper/dists/
```

### Verify in PyCache UI

1. Open `http://pycache.local/admin/tracker`
2. Run `./gradlew --version` 
3. Watch for `download_start` → `download_progress` → `download_complete` events
4. Check `http://pycache.local/info/by-source` → Gradle source → cached files

### Check Database

```bash
docker compose exec pycache sqlite3 /app/app/data/cache_server.db \
  "SELECT local_path, cached, size, last_checked FROM files WHERE local_path LIKE 'gradle%';"
```

---

## Configuration Reference

### PyCache Server URL Patterns

| Pattern | Example |
|---------|---------|
| Distribution | `http://pycache.local:80/cache/gradle/8.10/gradle-8.10-bin.zip` |
| All distributions | `http://pycache.local:80/cache/gradle/{version}/gradle-{version}-bin.zip` |
| Probe API | `POST http://pycache.local/api/probe {"local_path": "gradle/8.10/gradle-8.10-bin.zip"}` |
| Download API | `POST http://pycache.local/api/download {"local_path": "gradle/8.10/gradle-8.10-bin.zip"}` |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `GRADLE_USER_HOME` | Base directory for Gradle caches |
| `GRADLE_OPTS` | JVM options for Gradle daemon |
| `GRADLE_WRAPPER_VALIDATE_URL` | Disable URL validation (set to `false`) |

### Init Script Locations

| Scope | Location |
|-------|----------|
| User (Linux/macOS) | `~/.gradle/init.d/` |
| User (Windows) | `%USERPROFILE%\.gradle\init.d\` |
| System (Linux) | `/etc/gradle/init.d/` |
| Project | `<project>/gradle/init.d/` |

---

## Troubleshooting

### Issue: "Could not find distribution"

**Cause**: Version not in PyCache Gradle module
**Fix**: 
1. Check available versions: `curl http://pycache.local/api/sources`
2. Add version via Admin Panel → Sources → Gradle module → Edit
3. Or manually trigger download: `curl -X POST http://pycache.local/api/download -d '{"local_path":"gradle/8.11/gradle-8.11-bin.zip"}'`

### Issue: Wrapper still downloads from services.gradle.org

**Cause**: Init script not loaded or distributionUrl not matched
**Fix**:
1. Verify init script location: `ls -la ~/.gradle/init.d/`
2. Check Gradle logs: `./gradlew --version --debug 2>&1 | grep -i pycache`
3. Ensure `gradle.properties` doesn't override `distributionUrl`

### Issue: Permission denied on cache directory

**Cause**: `GRADLE_USER_HOME` not writable
**Fix**:
```bash
sudo chown -R $USER:$USER /var/cache/gradle-pycache
# or
chmod 777 ~/.gradle-pycache
```

### Issue: SSL/HTTPS errors

**Cause**: PyCache on HTTP but Gradle expects HTTPS
**Fix**: 
1. Use HTTP URL in distributionUrl (works for wrapper)
2. Or configure PyCache with SSL cert and use `https://pycache.local/cache/...`
3. Disable validation: `systemProp.gradle.wrapper.validateDistributionUrl=false`

### Issue: Gradle daemon caches old URL

**Cause**: Daemon running with old config
**Fix**:
```bash
./gradlew --stop
# Then rerun
./gradlew --version
```

---

## Best Practices

### For Teams

1. **Use Method 2 (Init Script)** - Automatic, zero project config
2. **Commit init script to repo** - `.gradle/init.d/pycache-distributions.gradle`
3. **Document PyCache URL** in project README

### For CI/CD

1. **Use Method 1 (GRADLE_USER_HOME)** - Isolated per job
2. **Cache the GRADLE_USER_HOME** between runs
3. **Pre-populate cache** in CI image

### For Air-Gapped

1. **Pre-populate PyCache** with all needed versions
2. **Use Method 2** with internal PyCache URL
3. **Disable upstream checks** in init script

---

## Quick Reference Card

```bash
# 1. Set up PyCache URL (replace with your host)
PYCACHE_URL="http://pycache.local:80"

# 2. Choose ONE method:

# METHOD 1: Environment variable (simplest)
export GRADLE_USER_HOME="$HOME/.gradle-pycache"
mkdir -p "$GRADLE_USER_HOME"
echo 'systemProp.gradle.wrapper.validateDistributionUrl=false' > "$GRADLE_USER_HOME/gradle.properties"

# METHOD 2: Init script (most powerful)
mkdir -p ~/.gradle/init.d
cat > ~/.gradle/init.d/pycache-distributions.gradle << 'EOF'
gradle.projectsLoaded {
    tasks.withType(Wrapper) { task ->
        def url = task.distributionUrl?.toString()
        if (url && url.contains("services.gradle.org")) {
            def version = (url =~ /gradle-([\d.]+)-/).find()[0][1]
            task.distributionUrl = "${System.getenv('PYCACHE_URL')}/cache/gradle/${version}/gradle-${version}-bin.zip"
        }
    }
}
EOF

# METHOD 3: Per-project (manual)
# Edit gradle/wrapper/gradle-wrapper.properties:
# distributionUrl=http://pycache.local:80/cache/gradle/8.10/gradle-8.10-bin.zip

# 3. Test
./gradlew --version

# 4. Verify in PyCache UI
open http://pycache.local/admin/tracker
```

---

## Related Documentation

- [Gradle Integration](./09-gradle-integration.md) - Project-level setup
- [Download System](./05-download-system.md) - How caching works
- [Admin Panel](./03-admin-panel.md) - Managing Gradle source
- [API Reference](./11-api-reference.md) - Programmatic access
- [Configuration](./10-configuration.md) - Environment variables