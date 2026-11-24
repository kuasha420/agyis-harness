    // AGYIS_REA_AUTODISCOVERY_V4: Multi-workspace dirtyroom & global registry direct-mount resolution
    const __agyisHasDotPart = (p) => {
        if (!p || typeof p !== "string") return true;
        return p.split(/[\\/]+/).some((seg) => seg.length > 1 && seg.startsWith(".") && seg !== "..");
    };
    const __agyisListGprs = (dirPath) => {
        try {
            if (!__agyisStatSync(dirPath).isDirectory()) return [];
            return __agyisReaddirSync(dirPath).filter((f) => f.endsWith(".gpr")).sort().map((f) => f.slice(0, -4));
        } catch (__listErr) {
            return [];
        }
    };
    const __agyisToNonDotDir = (dirPath) => {
        if (!dirPath || typeof dirPath !== "string") return undefined;
        try {
            const __norm = dirPath.replace(/[\\/]+$/, "");
            if (!__agyisHasDotPart(__norm)) return __norm;
            const __sameDir = (cand) => {
                try {
                    const __repStat = __agyisStatSync(cand);
                    if (!__repStat.isDirectory()) return false;
                    try {
                        const __origStat = __agyisStatSync(__norm);
                        if (__origStat.ino && __repStat.ino && (__origStat.ino !== __repStat.ino || __origStat.dev !== __repStat.dev)) {
                            return false;
                        }
                    } catch (__inoErr) {
                        return false;
                    }
                    return !__agyisHasDotPart(cand);
                } catch (__sameErr) {
                    return false;
                }
            };
            const __dirtyMatch = __norm.match(/^(.*?)(^|[\\/])\.dirtyroom($|[\\/].*)$/);
            const __aliasRoot = __dirtyMatch ? `${__dirtyMatch[1]}${__dirtyMatch[2]}dirtyroom` : undefined;
            const __replaced = __dirtyMatch ? `${__aliasRoot}${__dirtyMatch[3]}` : undefined;
            // (a) Existing sibling 'dirtyroom' symlink/alias
            if (__replaced && __sameDir(__replaced)) return __replaced;
            // (a2) Existing non-dot sibling for any other dot-prefixed directory component
            const __genericDotMatch = !__dirtyMatch ? __norm.match(/^(.*?)(^|[\\/])\.([^.\\/][^\\/]*)($|[\\/].*)$/) : null;
            if (__genericDotMatch) {
                const __genericCand = `${__genericDotMatch[1]}${__genericDotMatch[2]}${__genericDotMatch[3]}${__genericDotMatch[4]}`;
                if (__sameDir(__genericCand)) return __genericCand;
            }
            // (b) realpathSync if resolved path already has zero leading-dot components
            try {
                const __real = __agyisRealpathSync(__norm).replace(/[\\/]+$/, "");
                if (__real && !__agyisHasDotPart(__real) && __agyisStatSync(__real).isDirectory()) {
                    return __real;
                }
            } catch (__realErr) {
                // Fall through to sibling alias check
            }
            // (c) Create sibling 'dirtyroom -> .dirtyroom' symlink if absent and .gpr present (DEF-BB-038)
            if (__aliasRoot && __replaced && !__agyisHasDotPart(__replaced) && __agyisListGprs(__norm).length > 0) {
                let __aliasExists = false;
                try {
                    __agyisLstatSync(__aliasRoot);
                    __aliasExists = true;
                } catch (__lstatErr) {
                    __aliasExists = false;
                }
                if (!__aliasExists) {
                    try {
                        __agyisSymlinkSync(".dirtyroom", __aliasRoot, "dir");
                    } catch (__symErr) {
                        return undefined;
                    }
                }
                if (__sameDir(__replaced)) return __replaced;
            }
            return undefined;
        } catch (__ndErr) {
            return undefined;
        }
    };
    const __agyisInspectProjectPrograms = (projectDir, projName) => {
        try {
            const __idata = scriptPath.join(projectDir, `${projName}.rep`, "idata");
            if (!__agyisStatSync(__idata).isDirectory()) return null;
            const __programs = new Set();
            let __prpCount = 0;
            const __scanPrp = (filePath) => {
                if (__prpCount >= 128) return;
                __prpCount++;
                try {
                    const __xml = __agyisReadFileSync(filePath, "utf8");
                    const __typeM = __xml.match(/NAME="CONTENT_TYPE"\s+TYPE="string"\s+VALUE="([^"]+)"/i);
                    if (__typeM && __typeM[1] !== "Program") return;
                    const __nameM = __xml.match(/NAME="NAME"\s+TYPE="string"\s+VALUE="([^"]+)"/i);
                    if (__nameM && __nameM[1]) __programs.add(__nameM[1]);
                } catch (__prpErr) {
                    return;
                }
            };
            const __top = __agyisReaddirSync(__idata);
            for (const __entry of __top) {
                if (__prpCount >= 128) break;
                const __full = scriptPath.join(__idata, __entry);
                if (__entry.endsWith(".prp")) {
                    __scanPrp(__full);
                } else {
                    try {
                        if (__agyisStatSync(__full).isDirectory()) {
                            for (const __sub of __agyisReaddirSync(__full)) {
                                if (__prpCount >= 128) break;
                                if (__sub.endsWith(".prp")) __scanPrp(scriptPath.join(__full, __sub));
                            }
                        }
                    } catch (__subErr) {
                        continue;
                    }
                }
            }
            return __prpCount > 0 ? __programs : null;
        } catch (__inspErr) {
            return null;
        }
    };
    const __agyisSelectGpr = (projectDir, targetBase, explicitProjectName, allowUnmatched) => {
        const __gprs = __agyisListGprs(projectDir);
        if (__gprs.length === 0) return undefined;
        // Only bypass .rep/idata program verification when the caller passed options.existingProject directly
        if (explicitProjectName && allowUnmatched) {
            return __gprs.includes(explicitProjectName)
                ? { projectName: explicitProjectName, programName: targetBase }
                : undefined;
        }
        const __candidates = explicitProjectName
            ? (__gprs.includes(explicitProjectName) ? [explicitProjectName] : [])
            : __gprs;
        if (__candidates.length === 0) return undefined;
        let __ciMatch;
        let __syntheticFallback;
        const __targetLower = typeof targetBase === "string" ? targetBase.toLowerCase() : "";
        for (const __proj of __candidates) {
            const __progs = __agyisInspectProjectPrograms(projectDir, __proj);
            if (__progs === null) {
                try {
                    if (!__syntheticFallback && __agyisStatSync(scriptPath.join(projectDir, `${__proj}.rep`)).isDirectory()) {
                        __syntheticFallback = __proj;
                    }
                } catch (__repErr) {
                    // Orphan .gpr without a matching .rep directory cannot be mounted
                }
                continue;
            }
            if (__progs.has(targetBase)) return { projectName: __proj, programName: targetBase };
            if (!__ciMatch && __targetLower) {
                for (const __p of __progs) {
                    if (__p.toLowerCase() === __targetLower) {
                        __ciMatch = { projectName: __proj, programName: __p };
                        break;
                    }
                }
            }
        }
        if (__ciMatch) return __ciMatch;
        if (__syntheticFallback) return { projectName: __syntheticFallback, programName: targetBase };
        return allowUnmatched ? { projectName: __candidates[0], programName: targetBase } : undefined;
    };
    const __agyisDiscoverDirtyroom = (seedPaths, targetBase, explicitProjectName, allowUnmatched) => {
        for (const __rawSeed of seedPaths) {
            if (!__rawSeed || typeof __rawSeed !== "string") continue;
            let __curr = __rawSeed;
            try {
                if (typeof scriptPath.isAbsolute === "function" ? !scriptPath.isAbsolute(__rawSeed) : true) {
                    __curr = scriptPath.resolve(__rawSeed);
                }
            } catch (__resErr) {
                __curr = __rawSeed;
            }
            try {
                if (!__agyisStatSync(__curr).isDirectory()) {
                    __curr = scriptPath.dirname(__curr);
                }
            } catch (__stErr) {
                __curr = scriptPath.dirname(__curr);
            }
            for (let __depth = 0; __depth < 64 && __curr; __depth++) {
                let __foundLocalDir = false;
                const __preferred = scriptPath.join(__curr, "dirtyroom", "ghidra");
                if (__agyisListGprs(__preferred).length > 0) {
                    __foundLocalDir = true;
                    const __safePreferred = __agyisToNonDotDir(__preferred);
                    if (__safePreferred) {
                        const __sel = __agyisSelectGpr(__safePreferred, targetBase, explicitProjectName, allowUnmatched);
                        if (__sel) {
                            return { projectDir: __safePreferred, projectName: __sel.projectName, programName: __sel.programName };
                        }
                    }
                }
                const __dotCand = scriptPath.join(__curr, ".dirtyroom", "ghidra");
                if (__agyisListGprs(__dotCand).length > 0) {
                    __foundLocalDir = true;
                    const __safeDir = __agyisToNonDotDir(__dotCand);
                    if (__safeDir) {
                        const __sel = __agyisSelectGpr(__safeDir, targetBase, explicitProjectName, allowUnmatched);
                        if (__sel) {
                            return { projectDir: __safeDir, projectName: __sel.projectName, programName: __sel.programName };
                        }
                    }
                }
                if (__foundLocalDir) break;
                const __parent = scriptPath.dirname(__curr);
                if (!__parent || __parent === __curr) break;
                __curr = __parent;
            }
        }
        return undefined;
    };
    const __agyisHasConflictingSha = (binMap, progName, sha12) => {
        if (!sha12 || !binMap || typeof binMap !== "object") return false;
        const __progLower = progName.toLowerCase();
        let __sawSameName = false;
        for (const [__k, __v] of Object.entries(binMap)) {
            if (typeof __k === "string" && typeof __v === "string" && __v.toLowerCase() === __progLower) {
                if (__k.toLowerCase() === sha12) return false;
                __sawSameName = true;
            }
        }
        return __sawSameName;
    };
    const __agyisLookupRegistry = (targetPath, targetBase, explicitProjectName) => {
        try {
            const __stateDir = process.env.AGYIS_HARNESS_STATE_DIR || process.env.PSL_HARNESS_STATE_DIR;
            const __regPath = process.env.AGYIS_DIRTYROOM_REGISTRY || (
                __stateDir
                    ? __agyisOsJoin(__stateDir, "agyis_dirtyrooms.json")
                    : __agyisOsJoin(__agyisHomedir(), ".gemini", "config", "agyis_dirtyrooms.json")
            );
            if (!__regPath) return undefined;
            const __rawJson = __agyisReadFileSync(__regPath, "utf8");
            const __parsed = JSON.parse(__rawJson);
            const __rawMap = __parsed && typeof __parsed === "object" ? __parsed.dirtyrooms : undefined;
            if (!__rawMap || typeof __rawMap !== "object") return undefined;
            const __entries = (Array.isArray(__rawMap) ? __rawMap : Object.values(__rawMap))
                .filter((e) => e && typeof e === "object" && typeof e.ghidra_dir === "string")
                .sort((a, b) => (Number(b.last_seen) || 0) - (Number(a.last_seen) || 0))
                .slice(0, 64);
            if (__entries.length === 0) return undefined;
            const __baseForSha = typeof targetPath === "string" ? scriptPath.basename(targetPath) : "";
            const __shaM = __baseForSha.match(/^target-([0-9a-f]{12})(?:[._-]|$)/i);
            const __sha12 = __shaM ? __shaM[1].toLowerCase() : undefined;
            // Pass 1: Deterministic 12-hex SHA-256 prefix match across registered dirtyrooms
            if (__sha12) {
                for (const __entry of __entries) {
                    const __binMap = __entry.binaries;
                    if (!__binMap || typeof __binMap !== "object") continue;
                    let __mapped = __binMap[__sha12];
                    if (typeof __mapped !== "string") {
                        for (const [__k, __v] of Object.entries(__binMap)) {
                            if (typeof __k === "string" && __k.toLowerCase() === __sha12 && typeof __v === "string") {
                                __mapped = __v;
                                break;
                            }
                        }
                    }
                    if (typeof __mapped !== "string" || !__mapped) continue;
                    const __regDir = __agyisToNonDotDir(__entry.ghidra_dir);
                    if (!__regDir) continue;
                    const __sel = __agyisSelectGpr(__regDir, __mapped, explicitProjectName, false);
                    if (__sel) {
                        return { projectDir: __regDir, projectName: __sel.projectName, programName: __sel.programName };
                    }
                }
            }
            // Pass 2: Strict .rep/idata/*.prp program name match (rejects SHA conflicts; never hijacks unrelated binaries)
            const __targetLower = typeof targetBase === "string" && targetBase ? targetBase.toLowerCase() : "";
            if (__targetLower) {
                for (const __entry of __entries) {
                    const __regDir = __agyisToNonDotDir(__entry.ghidra_dir);
                    if (!__regDir) continue;
                    const __gprs = __agyisListGprs(__regDir);
                    for (const __proj of __gprs) {
                        if (explicitProjectName && __proj !== explicitProjectName) continue;
                        const __progs = __agyisInspectProjectPrograms(__regDir, __proj);
                        if (__progs === null) continue;
                        if (__progs.has(targetBase) && !__agyisHasConflictingSha(__entry.binaries, targetBase, __sha12)) {
                            return { projectDir: __regDir, projectName: __proj, programName: targetBase };
                        }
                        for (const __p of __progs) {
                            if (__p.toLowerCase() === __targetLower && !__agyisHasConflictingSha(__entry.binaries, __p, __sha12)) {
                                return { projectDir: __regDir, projectName: __proj, programName: __p };
                            }
                        }
                    }
                }
            }
        } catch (__regErr) {
            return undefined;
        }
        return undefined;
    };
    const __agyisHasImportOverride = Boolean(
        options.rawBinary ||
        options.dosMz ||
        options.dosCom ||
        options.gamecubeDol !== undefined ||
        options.psp === true ||
        options.packedProgramPath !== undefined ||
        options.languageOverride !== undefined ||
        options.mipsSoftFloat === true ||
        options.riscvCallingConvention !== undefined ||
        options.seedPath !== undefined ||
        (options.disabledAnalyzers?.length ?? 0) > 0
    );
    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0" && !__agyisHasImportOverride) {
        const __originTargetPath = (globalThis.__agyisReaSnapshotOrigin && globalThis.__agyisReaSnapshotOrigin.get(options.targetPath)) || options.targetPath;
        const __rawRequestedPath =
            (globalThis.__agyisReaRequestedPath && (
                globalThis.__agyisReaRequestedPath.get(__originTargetPath) ||
                globalThis.__agyisReaRequestedPath.get(options.targetPath)
            )) || undefined;
        let targetBase = scriptPath.basename(__originTargetPath);
        const BINARY_MAP = {};
        if (process.env.REA_BINARY_MAP) {
            try {
                const __parsedMap = JSON.parse(process.env.REA_BINARY_MAP);
                if (__parsedMap && typeof __parsedMap === "object" && !Array.isArray(__parsedMap)) {
                    Object.assign(BINARY_MAP, __parsedMap);
                }
            } catch (__mapErr) {
                // Ignore malformed REA_BINARY_MAP JSON
            }
        }
        if (process.env.REA_GHIDRA_PROGRAM_NAME) {
            targetBase = process.env.REA_GHIDRA_PROGRAM_NAME;
        } else if (options.existingProject?.programName) {
            targetBase = options.existingProject.programName;
        } else {
            const __rawBase = scriptPath.basename(options.targetPath);
            if (__rawBase.startsWith("target-")) {
                const __prefix = __rawBase.slice(7, 19);
                if (typeof BINARY_MAP[__prefix] === "string" && BINARY_MAP[__prefix]) {
                    targetBase = BINARY_MAP[__prefix];
                }
            }
        }
        let projectDir;
        let projectName = options.existingProject?.projectName || process.env.REA_GHIDRA_PROJECT_NAME || process.env.AGYIS_DIRTYROOM_PROJECT || undefined;
        // Only explicit options.existingProject may bypass .rep/idata program membership verification.
        // Global env vars (AGYIS_DIRTYROOM, REA_GHIDRA_PROJECT_DIR, etc.) must verify membership against .rep/idata/*.prp.
        const __allowUnmatched = Boolean(options.existingProject);
        if (options.existingProject?.projectPath) {
            projectDir = __agyisToNonDotDir(options.existingProject.projectPath);
        } else if (process.env.REA_GHIDRA_PROJECT_DIR) {
            projectDir = __agyisToNonDotDir(process.env.REA_GHIDRA_PROJECT_DIR);
        } else if (process.env.REA_GHIDRA_PROJECT_PATH) {
            const __pPath = process.env.REA_GHIDRA_PROJECT_PATH;
            if (__pPath.endsWith(".gpr")) {
                projectDir = __agyisToNonDotDir(scriptPath.dirname(__pPath));
                if (!projectName) projectName = scriptPath.basename(__pPath, ".gpr");
            } else {
                projectDir = __agyisToNonDotDir(__pPath);
            }
        } else if (process.env.AGYIS_DIRTYROOM) {
            projectDir = __agyisToNonDotDir(scriptPath.join(process.env.AGYIS_DIRTYROOM, "ghidra"));
        } else if (process.env.REA_DIRTYROOM) {
            projectDir = __agyisToNonDotDir(scriptPath.join(process.env.REA_DIRTYROOM, "ghidra"));
        } else {
            let __safeCwd;
            try { __safeCwd = process.cwd(); } catch (__cwdErr) { __safeCwd = undefined; }
            const __discovered = __agyisDiscoverDirtyroom([__rawRequestedPath, __originTargetPath, options.targetPath, __safeCwd], targetBase, projectName, __allowUnmatched);
            if (__discovered) {
                projectDir = __discovered.projectDir;
                if (!projectName) projectName = __discovered.projectName;
                if (__discovered.programName && !process.env.REA_GHIDRA_PROGRAM_NAME && !options.existingProject?.programName) {
                    targetBase = __discovered.programName;
                }
            } else {
                const __regHit = __agyisLookupRegistry(options.targetPath, targetBase, projectName);
                if (__regHit) {
                    projectDir = __regHit.projectDir;
                    if (!projectName) projectName = __regHit.projectName;
                    if (__regHit.programName && !process.env.REA_GHIDRA_PROGRAM_NAME && !options.existingProject?.programName) {
                        targetBase = __regHit.programName;
                    }
                }
            }
        }
        if (projectDir) {
            try {
                const activeSel = __agyisSelectGpr(projectDir, targetBase, projectName, __allowUnmatched);
                if (activeSel) {
                    const activeProject = activeSel.projectName;
                    if (activeSel.programName && !process.env.REA_GHIDRA_PROGRAM_NAME && !options.existingProject?.programName) {
                        targetBase = activeSel.programName;
                    }
                    const gprPath = scriptPath.join(projectDir, `${activeProject}.gpr`);
                    __agyisStatSync(gprPath);
                    return [
                        projectDir,
                        activeProject,
                        "-process",
                        targetBase,
                        "-noanalysis",
                        "-readOnly",
                        "-log",
                        options.ghidraLogPath,
                        "-scriptlog",
                        options.scriptLogPath,
                        "-scriptPath",
                        bridgeDirectory,
                        "-postScript",
                        options.bridgeScriptPath,
                        options.descriptorPath
                    ];
                }
            } catch (__mountErr) {
                // Fall through to size guard / standard launcher
            }
        }
        // PSL-RE-001 §1 Guard: Refuse ad-hoc headless -import on large (>10MB) binaries lacking a matching pre-analyzed .gpr
        if (!options.existingProject) {
            const __guardPath = typeof __originTargetPath === "string" && __originTargetPath ? __originTargetPath : options.targetPath;
            if (typeof __guardPath === "string" && __guardPath) {
                try {
                    const __guardStat = __agyisStatSync(__guardPath);
                    if (__guardStat.isFile() && __guardStat.size > 10 * 1024 * 1024) {
                        const __sizeMb = (__guardStat.size / (1024 * 1024)).toFixed(1);
                        throw new Error(
                            `PSL-RE-001 §1 Violation: Target binary '${scriptPath.basename(__guardPath)}' (${__sizeMb} MB) exceeds 10MB and has no matching pre-analyzed Ghidra project (.gpr/.rep). Run 'agyis re pre-analyze' before decompiling.`
                        );
                    }
                } catch (__sizeErr) {
                    if (__sizeErr && typeof __sizeErr.message === "string" && __sizeErr.message.startsWith("PSL-RE-001")) {
                        throw __sizeErr;
                    }
                }
            }
        }
    }
