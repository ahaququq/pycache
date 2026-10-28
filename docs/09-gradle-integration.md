# Gradle Integration

## Overview

PyCache includes a test Gradle project configured to download Gradle distributions from the PyCache cache server instead of the official Gradle distribution server.

## Test Project Location

```
/home/ahaququq/Dokumenty/Yapping/PyCache/test-gradle-project/
```

## Project Structure

```
test-gradle-project/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/java/com/example/Main.java
│   └── test/java/com/example/MainTest.java
├── build.gradle
├── gradlew
├── gradlew.bat
└── README.md
```

## Configuration

### Gradle Wrapper Properties

File: `test-gradle-project/gradle/wrapper/gradle-wrapper.properties`

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

### Key Settings

| Property | Value | Description |
|----------|-------|-------------|
| `distributionUrl` | `http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip` | Points to PyCache cache |
| `distributionBase` | `GRADLE_USER_HOME` | Standard Gradle location |
| `distributionPath` | `wrapper/dists` | Standard Gradle location |

## Usage

### Build Project

```bash
cd /home/ahaququq/Dokumenty/Yapping/PyCache/test-gradle-project

# First run - downloads from PyCache cache
./gradlew build

# Subsequent runs use Gradle's local cache
./gradlew build
```

### Change Gradle Version

Edit `gradle/wrapper/gradle-wrapper.properties`:

```properties
# For Gradle 8.5
distributionUrl=http://localhost:80/cache/gradle/8.5/gradle-8.5-bin.zip

# For Gradle 8.10
distributionUrl=http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip

# For Gradle 7.6
distributionUrl=http://localhost:80/cache/gradle/7.6/gradle-7.6-bin.zip
```

Then run:
```bash
./gradlew wrapper --gradle-version 8.5
```

## How It Works

### Download Flow

```
./gradlew build
       │
       ▼
Gradle reads distributionUrl
       │
       ▼
HTTP GET http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip
       │
       ▼
PyCache serve_cached() 
       │
       ├─ Cached? ──Yes──▶ Serve from /app/app/cache/
       │
       └─ No ──▶ Download from services.gradle.org
                        │
                        ▼
                   Cache to /app/app/cache/
                        │
                        ▼
                   Serve file
```

### First Run (Cache Miss)

```
./gradlew build
# Output:
# Downloading http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip
# .............10%...........20%...........100%
# 
# Welcome to Gradle 8.10!
# BUILD SUCCESSFUL in 15s
```

### Subsequent Runs (Cache Hit)

```
./gradlew build
# Output:
# BUILD SUCCESSFUL in 2s
```

## Wrapper Files

### gradle-wrapper.properties
```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

### gradle-wrapper.jar
Standard Gradle wrapper JAR (downloaded from Gradle release)

### gradlew / gradlew.bat
Standard Gradle wrapper scripts

## Available Gradle Versions

Check available versions:
```bash
curl -s http://localhost/api/sources | jq '.[] | select(.kind=="gradle")'
```

Or browse: `http://localhost:80/info/by-source` → Click "gradle_dist"

### Common Versions

| Version | URL |
|---------|-----|
| 8.10 | `http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip` |
| 8.5 | `http://localhost:80/cache/gradle/8.5/gradle-8.5-bin.zip` |
| 8.0 | `http://localhost:80/cache/gradle/8.0/gradle-8.0-bin.zip` |
| 7.6 | `http://localhost:80/cache/gradle/7.6/gradle-7.6-bin.zip` |
| 7.0 | `http://localhost:80/cache/gradle/7.0/gradle-7.0-bin.zip` |

## Wrapper Update

```bash
# Update to specific version
./gradlew wrapper --gradle-version 8.10

# Or manually edit gradle/wrapper/gradle-wrapper.properties
# Then run:
./gradlew wrapper
```

## Testing Download

```bash
# Test download via API
curl -X POST http://localhost/api/download \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.10/gradle-8.10-bin.zip"}'

# Test probe
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.10/gradle-8.10-bin.zip"}'
```

## Wrapper Files

### Required Files
```
gradle/
└── wrapper/
    ├── gradle-wrapper.jar      # Standard Gradle wrapper JAR
    └── gradle-wrapper.properties  # Configuration
```

### gradle-wrapper.jar
Downloaded from: `https://github.com/gradle/gradle/raw/v{version}/gradle/wrapper/gradle-wrapper.jar`

### gradlew / gradlew.bat
Standard Gradle wrapper scripts (executable)

## Windows Support

```cmd
# Windows
gradlew.bat build

# Linux/macOS
./gradlew build
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Check PyCache is running: `docker compose ps` |
| 404 on download | Check if version exists in PyCache sources |
| Permission denied | `chmod +x gradlew` |
| Cache not working | Check `/admin/tracker` for download events |
| Version not found | Add version to Gradle source or use DB source |

## Build Process

```
./gradlew build
  │
  ├─▶ Download Gradle distribution (if not cached)
  ├─▶ Download dependencies (Maven Central)
  ├─▶ Compile Java sources
  ├─▶ Run tests
  └─▶ Package JAR
```

## Cache Verification

```bash
# Check cache
ls -la /home/ahaququq/Dokumenty/Yapping/PyCache/test-gradle-project/.gradle/wrapper/dists/

# Check PyCache cache
docker compose exec pycache ls -la /app/app/cache/ | grep gradle
```

## Configuration for Other Projects

To use PyCache in another Gradle project:

1. Copy `gradle/wrapper/` to your project
2. Edit `gradle/wrapper/gradle-wrapper.properties`:
   ```properties
   distributionUrl=http://your-pycache-host:80/cache/gradle/8.10/gradle-8.10-bin.zip
   ```
3. Run `./gradlew wrapper` to regenerate scripts
4. Commit wrapper files to version control

## Network Configuration

For remote access, replace `localhost` with your PyCache host:
```properties
distributionUrl=http://pycache.local:80/cache/gradle/8.10/gradle-8.10-bin.zip
```

Or use environment variable in CI/CD:
```yaml
# GitHub Actions
- name: Build with Gradle
  run: ./gradlew build
  env:
    GRADLE_USER_HOME: ${{ runner.temp }}/gradle
  env:
    GRADLE_OPTS: "-Dgradle.user.home=${{ runner.temp }}/gradle"
```

## Verification

```bash
# Verify cached file
ls -la /app/app/cache/ | grep gradle

# Check database
docker compose exec pycache sqlite3 /app/app/data/cache_server.db \
  "SELECT local_path, cached, size FROM files WHERE local_path LIKE 'gradle%';"
```