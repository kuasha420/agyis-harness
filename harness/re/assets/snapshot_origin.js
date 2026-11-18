    // AGYIS_REA_AUTODISCOVERY_V4: Record original binary path for direct-mount discovery
    try {
        const __agyisOriginMap = (globalThis.__agyisReaSnapshotOrigin ??= new Map());
        __agyisOriginMap.delete(snapshotPath);
        if (__agyisOriginMap.size >= 64) {
            const __oldestKey = __agyisOriginMap.keys().next().value;
            if (__oldestKey !== undefined) __agyisOriginMap.delete(__oldestKey);
        }
        __agyisOriginMap.set(snapshotPath, sourcePath);
    } catch {}
