    // AGYIS_REA_AUTODISCOVERY_V4: Zero-copy direct-mount fingerprint bypass
    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0" && typeof root === "string" && root.length > 0) {
        let __agyisBypass = false;
        try {
            const __resolved = __agyisResolve(root);
            const __st = await __agyisStat(__resolved);
            if (__st.isDirectory()) {
                if (typeof name === "string" && name.length > 0) {
                    const __gprSt = await __agyisStat(__agyisJoin(__resolved, `${name}.gpr`));
                    const __repSt = await __agyisStat(__agyisJoin(__resolved, `${name}.rep`));
                    if (__gprSt.isFile() && __repSt.isDirectory()) {
                        __agyisBypass = true;
                    }
                } else {
                    const __directEntries = await __agyisReaddir(__resolved);
                    for (const __entry of __directEntries) {
                        if (!__entry.endsWith(".gpr")) continue;
                        const __stem = __entry.slice(0, -4);
                        try {
                            const __gprSt = await __agyisStat(__agyisJoin(__resolved, __entry));
                            const __repSt = await __agyisStat(__agyisJoin(__resolved, `${__stem}.rep`));
                            if (__gprSt.isFile() && __repSt.isDirectory()) {
                                __agyisBypass = true;
                                break;
                            }
                        } catch (__entryErr) {
                            if (__entryErr && __entryErr.code !== "ENOENT" && __entryErr.code !== "ENOTDIR") {
                                break;
                            }
                        }
                    }
                }
            }
        } catch (__fpErr) {
            if (__fpErr && __fpErr.code !== "ENOENT" && __fpErr.code !== "ENOTDIR" && __fpErr.code !== "EACCES") {
                __agyisBypass = false;
            }
        }
        if (__agyisBypass) {
            return "0000000000000000000000000000000000000000000000000000000000000000"; // REA_DIRECT_MOUNT_ACTIVE: 64-hex SHA256 bypass
        }
    }
