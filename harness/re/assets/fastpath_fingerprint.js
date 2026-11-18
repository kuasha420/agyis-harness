    // AGYIS_REA_AUTODISCOVERY_V4: Zero-copy direct-mount fingerprint bypass
    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0") {
        let __agyisBypass = Boolean(
            process.env.REA_GHIDRA_PROJECT_DIR ||
            process.env.REA_GHIDRA_PROJECT_PATH ||
            process.env.AGYIS_DIRTYROOM ||
            process.env.IMMORTAL_DIRTYROOM ||
            process.env.REA_DIRTYROOM
        );
        if (!__agyisBypass) {
            let __targetPath = typeof root === "string" && root.length > 0 ? root : undefined;
            if (!__targetPath) {
                try { __targetPath = process.cwd(); } catch {}
            }
            if (__targetPath) {
                try {
                    const __resolved = __agyisResolve(__targetPath);
                    const __st = await __agyisStat(__resolved);
                    if (__st.isDirectory()) {
                        try {
                            const __directEntries = await __agyisReaddir(__resolved);
                            if (__directEntries.some((f) => f.endsWith(".gpr"))) {
                                __agyisBypass = true;
                            }
                        } catch {}
                    }
                    let __curr = __st.isDirectory() ? __resolved : __agyisDirname(__resolved);
                    for (let __d = 0; __d < 64 && __curr && !__agyisBypass; __d++) {
                        for (const __cand of [__agyisJoin(__curr, "dirtyroom", "ghidra"), __agyisJoin(__curr, ".dirtyroom", "ghidra")]) {
                            try {
                                const __entries = await __agyisReaddir(__cand);
                                if (__entries.some((f) => f.endsWith(".gpr"))) {
                                    __agyisBypass = true;
                                    break;
                                }
                            } catch {}
                        }
                        if (__agyisBypass) break;
                        const __parent = __agyisDirname(__curr);
                        if (!__parent || __parent === __curr) break;
                        __curr = __parent;
                    }
                } catch {}
            }
        }
        if (__agyisBypass) {
            return "0000000000000000000000000000000000000000000000000000000000000000"; // REA_DIRECT_MOUNT_ACTIVE: 64-hex SHA256 bypass
        }
    }
