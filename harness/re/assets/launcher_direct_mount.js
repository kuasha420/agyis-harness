    // AGYIS_REA_AUTODISCOVERY_V3: Multi-workspace dirtyroom direct-mount resolution
    const __agyisToNonDotDir = (dirPath) => {
        if (!dirPath || typeof dirPath !== "string") return undefined;
        try {
            const __norm = dirPath.replace(/[\\/]+$/, "");
            const __match = __norm.match(/^(.*?)(^|[\\/])\.dirtyroom($|[\\/].*)$/);
            if (!__match) return __norm;
            const __aliasRoot = `${__match[1]}${__match[2]}dirtyroom`;
            const __replaced = `${__aliasRoot}${__match[3]}`;
            try {
                __agyisLstatSync(__aliasRoot);
            } catch {
                try {
                    __agyisSymlinkSync(".dirtyroom", __aliasRoot, "dir");
                } catch {}
            }
            try {
                const __repStat = __agyisStatSync(__replaced);
                if (__repStat.isDirectory()) {
                    try {
                        const __origStat = __agyisStatSync(__norm);
                        if (__origStat.ino && __repStat.ino && (__origStat.ino !== __repStat.ino || __origStat.dev !== __repStat.dev)) {
                            return undefined;
                        }
                    } catch {}
                    return __replaced;
                }
            } catch {}
            return undefined;
        } catch {
            return undefined;
        }
    };
    const __agyisListGprs = (dirPath) => {
        try {
            if (!__agyisStatSync(dirPath).isDirectory()) return [];
            return __agyisReaddirSync(dirPath).filter((f) => f.endsWith(".gpr")).sort().map((f) => f.slice(0, -4));
        } catch {
            return [];
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
                } catch {}
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
                    } catch {}
                }
            }
            return __prpCount > 0 ? __programs : null;
        } catch {
            return null;
        }
    };
    const __agyisSelectGpr = (projectDir, targetBase, explicitProjectName, allowUnmatched) => {
        const __gprs = __agyisListGprs(projectDir);
        if (__gprs.length === 0) return undefined;
        if (explicitProjectName) {
            return __gprs.includes(explicitProjectName) ? explicitProjectName : undefined;
        }
        let __ciMatch;
        let __syntheticFallback;
        const __targetLower = typeof targetBase === "string" ? targetBase.toLowerCase() : "";
        for (const __proj of __gprs) {
            const __progs = __agyisInspectProjectPrograms(projectDir, __proj);
            if (__progs === null) {
                if (!__syntheticFallback) __syntheticFallback = __proj;
                continue;
            }
            if (__progs.has(targetBase)) return __proj;
            if (!__ciMatch && __targetLower) {
                for (const __p of __progs) {
                    if (__p.toLowerCase() === __targetLower) {
                        __ciMatch = __proj;
                        break;
                    }
                }
            }
        }
        if (__ciMatch) return __ciMatch;
        if (__syntheticFallback) return __syntheticFallback;
        return allowUnmatched ? __gprs[0] : undefined;
    };
    const __agyisDiscoverDirtyroom = (seedPaths, targetBase, explicitProjectName, allowUnmatched) => {
        for (const __rawSeed of seedPaths) {
            if (!__rawSeed || typeof __rawSeed !== "string") continue;
            let __curr = __rawSeed;
            try {
                if (typeof scriptPath.isAbsolute === "function" ? !scriptPath.isAbsolute(__rawSeed) : true) {
                    __curr = scriptPath.resolve(__rawSeed);
                }
            } catch {}
            try {
                if (!__agyisStatSync(__curr).isDirectory()) {
                    __curr = scriptPath.dirname(__curr);
                }
            } catch {
                __curr = scriptPath.dirname(__curr);
            }
            for (let __depth = 0; __depth < 64 && __curr; __depth++) {
                const __preferred = scriptPath.join(__curr, "dirtyroom", "ghidra");
                const __prefGprs = __agyisListGprs(__preferred);
                if (__prefGprs.length > 0) {
                    const __sel = __agyisSelectGpr(__preferred, targetBase, explicitProjectName, allowUnmatched);
                    return __sel ? { projectDir: __preferred, projectName: __sel } : undefined;
                }
                const __dotCand = scriptPath.join(__curr, ".dirtyroom", "ghidra");
                const __dotGprs = __agyisListGprs(__dotCand);
                if (__dotGprs.length > 0) {
                    const __safeDir = __agyisToNonDotDir(__dotCand);
                    if (!__safeDir) return undefined;
                    const __sel = __agyisSelectGpr(__safeDir, targetBase, explicitProjectName, allowUnmatched);
                    return __sel ? { projectDir: __safeDir, projectName: __sel } : undefined;
                }
                const __parent = scriptPath.dirname(__curr);
                if (!__parent || __parent === __curr) break;
                __curr = __parent;
            }
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
        let targetBase = scriptPath.basename(__originTargetPath);
        const BINARY_MAP = {
            "0c51d381dfe9": "ShippingPC-ChaosGame.exe",
            "90ce02b7b820": "MctsInterface.dll",
            "1c4ad378fb8c": "vivoxsdk_x64.dll"
        };
        if (process.env.REA_BINARY_MAP) {
            try { Object.assign(BINARY_MAP, JSON.parse(process.env.REA_BINARY_MAP)); } catch {}
        }
        if (process.env.REA_GHIDRA_PROGRAM_NAME) {
            targetBase = process.env.REA_GHIDRA_PROGRAM_NAME;
        } else if (options.existingProject?.programName) {
            targetBase = options.existingProject.programName;
        } else {
            const __rawBase = scriptPath.basename(options.targetPath);
            if (__rawBase.startsWith("target-")) {
                const __prefix = __rawBase.slice(7, 19);
                if (BINARY_MAP[__prefix]) {
                    targetBase = BINARY_MAP[__prefix];
                }
            }
        }
        let projectDir;
        let projectName = options.existingProject?.projectName || process.env.REA_GHIDRA_PROJECT_NAME || (process.env.AGYIS_DIRTYROOM_PROJECT || (process.env.IMMORTAL_DIRTYROOM ? "PaladinsProject" : undefined));
        const __allowUnmatched = Boolean(
            options.existingProject ||
            process.env.REA_GHIDRA_PROGRAM_NAME ||
            process.env.REA_GHIDRA_PROJECT_NAME ||
            process.env.REA_GHIDRA_PROJECT_DIR ||
            process.env.REA_GHIDRA_PROJECT_PATH ||
            process.env.AGYIS_DIRTYROOM ||
            process.env.IMMORTAL_DIRTYROOM ||
            process.env.REA_DIRTYROOM
        );
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
        } else if (process.env.IMMORTAL_DIRTYROOM) {
            projectDir = __agyisToNonDotDir(scriptPath.join(process.env.IMMORTAL_DIRTYROOM, "ghidra"));
        } else if (process.env.REA_DIRTYROOM) {
            projectDir = __agyisToNonDotDir(scriptPath.join(process.env.REA_DIRTYROOM, "ghidra"));
        } else {
            let __safeCwd;
            try { __safeCwd = process.cwd(); } catch {}
            const __discovered = __agyisDiscoverDirtyroom([__originTargetPath, options.targetPath, __safeCwd], targetBase, projectName, __allowUnmatched);
            if (__discovered) {
                projectDir = __discovered.projectDir;
                if (!projectName) projectName = __discovered.projectName;
            }
        }
        if (projectDir) {
            try {
                const activeProject = __agyisSelectGpr(projectDir, targetBase, projectName, __allowUnmatched);
                if (activeProject) {
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
            } catch {}
        }
    }
