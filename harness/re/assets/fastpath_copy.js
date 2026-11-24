    // AGYIS_REA_AUTODISCOVERY_V4: Zero-copy direct-mount disk clone bypass
    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0" && typeof sourcePath === "string" && sourcePath.length > 0) {
        let __agyisBypass = false;
        try {
            const __resolved = __agyisResolve(sourcePath);
            const __st = await __agyisStat(__resolved);
            let __projDir;
            let __projName = typeof options?.projectName === "string" && options.projectName.length > 0 ? options.projectName : undefined;
            if (__st.isFile() && __resolved.endsWith(".gpr")) {
                __projDir = __agyisDirname(__resolved);
                if (!__projName) {
                    const __base = __resolved.slice(__projDir.length + 1);
                    __projName = __base.slice(0, -4);
                }
            } else if (__st.isDirectory()) {
                __projDir = __resolved;
            }
            if (__projDir) {
                if (__projName) {
                    const __gprSt = await __agyisStat(__agyisJoin(__projDir, `${__projName}.gpr`));
                    const __repSt = await __agyisStat(__agyisJoin(__projDir, `${__projName}.rep`));
                    if (__gprSt.isFile() && __repSt.isDirectory()) {
                        __agyisBypass = true;
                    }
                } else {
                    const __entries = await __agyisReaddir(__projDir);
                    for (const __entry of __entries) {
                        if (!__entry.endsWith(".gpr")) continue;
                        const __stem = __entry.slice(0, -4);
                        try {
                            const __gprSt = await __agyisStat(__agyisJoin(__projDir, __entry));
                            const __repSt = await __agyisStat(__agyisJoin(__projDir, `${__stem}.rep`));
                            if (__gprSt.isFile() && __repSt.isDirectory()) {
                                __projName = __stem;
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
                if (__agyisBypass && __projName && typeof options?.programName === "string" && options.programName.length > 0) {
                    try {
                        const __idata = __agyisJoin(__projDir, `${__projName}.rep`, "idata");
                        const __idataSt = await __agyisStat(__idata);
                        if (__idataSt.isDirectory()) {
                            const __progs = new Set();
                            let __prpCount = 0;
                            const __scanPrp = async (prpPath) => {
                                if (__prpCount >= 128) return;
                                __prpCount++;
                                try {
                                    const __xml = await __agyisReadFile(prpPath, "utf8");
                                    const __typeM = __xml.match(/NAME="CONTENT_TYPE"\s+TYPE="string"\s+VALUE="([^"]+)"/i);
                                    if (__typeM && __typeM[1] !== "Program") return;
                                    const __nameM = __xml.match(/NAME="NAME"\s+TYPE="string"\s+VALUE="([^"]+)"/i);
                                    if (__nameM && __nameM[1]) __progs.add(__nameM[1].toLowerCase());
                                } catch (__readErr) {
                                    if (__readErr && __readErr.code !== "ENOENT") return;
                                }
                            };
                            const __top = await __agyisReaddir(__idata);
                            for (const __entry of __top) {
                                if (__prpCount >= 128) break;
                                const __full = __agyisJoin(__idata, __entry);
                                if (__entry.endsWith(".prp")) {
                                    await __scanPrp(__full);
                                } else {
                                    try {
                                        if ((await __agyisStat(__full)).isDirectory()) {
                                            for (const __sub of await __agyisReaddir(__full)) {
                                                if (__prpCount >= 128) break;
                                                if (__sub.endsWith(".prp")) await __scanPrp(__agyisJoin(__full, __sub));
                                            }
                                        }
                                    } catch (__subErr) {
                                        if (__subErr && __subErr.code !== "ENOENT") continue;
                                    }
                                }
                            }
                            if (__prpCount > 0 && !__progs.has(options.programName.toLowerCase())) {
                                __agyisBypass = false;
                            }
                        }
                    } catch (__idataErr) {
                        if (__idataErr && __idataErr.code !== "ENOENT" && __idataErr.code !== "ENOTDIR") {
                            __agyisBypass = false;
                        }
                    }
                }
            }
        } catch (__cpErr) {
            if (__cpErr && __cpErr.code !== "ENOENT" && __cpErr.code !== "ENOTDIR" && __cpErr.code !== "EACCES") {
                __agyisBypass = false;
            }
        }
        if (__agyisBypass) {
            return; // REA_DIRECT_MOUNT_ACTIVE: Bypass 1.3GB disk copy
        }
    }
