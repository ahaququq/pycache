# Test Gradle Project for PyCache Integration

This is a simple test project to verify that Gradle can download distributions from PyCache.

## Quick Start

### Linux/macOS
```bash
./gradlew --version
```

### Windows
```cmd
gradlew.bat --version
```

The wrapper is configured to download Gradle distributions from the PyCache server at `http://localhost:80/cache/` instead of the official `services.gradle.org`.

## Configuration

The key configuration is in `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip
```

This tells Gradle to download the distribution from PyCache. The path structure matches what PyCache's Gradle module provides:
- Local path: `gradle/{version}/gradle-{version}-bin.zip`
- Cached at: `/cache/gradle/{version}/gradle-{version}-bin.zip`

## How It Works

1. When you run `./gradlew` for the first time, it reads `distributionUrl` from the wrapper properties
2. Gradle downloads the distribution from `http://localhost:80/cache/gradle/8.10/gradle-8.10-bin.zip`
3. PyCache checks if the file is already cached
4. If not cached, PyCache fetches it from `https://services.gradle.org/distributions/gradle-8.10-bin.zip`, caches it, and serves it
5. Subsequent runs use the cached version instantly

## Using Different Gradle Versions

To use a different Gradle version, update `gradle/wrapper/gradle-wrapper.properties`:

```properties
# For Gradle 8.5
distributionUrl=http://localhost:80/cache/gradle/8.5/gradle-8.5-bin.zip

# For Gradle 7.6
distributionUrl=http://localhost:80/cache/gradle/7.6/gradle-7.6-bin.zip

# For any version available on services.gradle.org
distributionUrl=http://localhost:80/cache/gradle/{version}/gradle-{version}-bin.zip
```

Then run `./gradlew wrapper --gradle-version {version}` to update the wrapper, or manually edit the properties file.

## Available Versions

Check available versions at:
- `http://localhost:80/info/by-source` (click on "gradle" source)
- `http://localhost:80/api/sources` (JSON)

Or use the admin panel: `http://localhost:80/admin/modules` → View gradle module

## Windows Notes

On Windows, the wrapper script is `gradlew.bat`. It works the same way - just run:
```cmd
gradlew.bat --version
gradlew.bat build
```

## Troubleshooting

If you get connection errors:
1. Ensure PyCache is running: `docker compose up -d`
2. Check health: `curl http://localhost/health`
3. Verify the gradle source is configured in admin panel: `http://localhost:80/admin/sources`
4. Check if the distribution exists in PyCache: `curl http://localhost:80/info/by-source/1` (where 1 is the gradle source ID)

If the distribution is not cached yet, the first download will be slower as PyCache fetches from upstream.