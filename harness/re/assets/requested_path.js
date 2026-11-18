    // AGYIS_REA_AUTODISCOVERY_V4: Record pre-realpath caller path for symlinked dirtyroom discovery
    try {
        const __agyisReqMap = (globalThis.__agyisReaRequestedPath ??= new Map());
        __agyisReqMap.delete(canonical);
        if (__agyisReqMap.size >= 64) {
            const __oldestReq = __agyisReqMap.keys().next().value;
            if (__oldestReq !== undefined) __agyisReqMap.delete(__oldestReq);
        }
        __agyisReqMap.set(canonical, candidate);
    } catch {}
