import sqlite3
import json

conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()

c.execute('''
SELECT 
    tc.id, tc.session_id, tc.step_index, tc.tool_name, 
    tc.command_line, tc.target_path, tc.arguments_json, tc.error_snippet,
    s.start_time
FROM tool_calls tc
JOIN sessions s ON tc.session_id = s.session_id
WHERE s.start_time >= '2026-10-02'
  AND tc.error_snippet LIKE '%denied by pre-tool hook%'
ORDER BY s.start_time, tc.session_id, tc.step_index
''')

denials = c.fetchall()
print(f"Total Pre-Tool Hook Denials: {len(denials)}")

categories = {
    "TDD / Test Verification": [],
    "Teamwork Liveness / Heartbeat (progress.md)": [],
    "Background Task Status / Log Polling": [],
    "Routine Git Lifecycle (git status, diff)": [],
    "Genuine Runaway Loops / Repeating Thrashing": [],
    "Other": []
}

for d in denials:
    tid, sid, step, tool, cmd, target, args_json, err, start = d
    args = json.loads(args_json) if args_json else {}
    
    # Classify
    cmd_str = cmd or args.get("CommandLine", "")
    target_str = target or args.get("AbsolutePath", "") or args.get("TargetFile", "")
    action_str = args.get("Action", "")
    
    cat = "Other"
    if "progress.md" in target_str or "progress.md" in cmd_str:
        cat = "Teamwork Liveness / Heartbeat (progress.md)"
    elif tool == "manage_task" and action_str == "status":
        cat = "Background Task Status / Log Polling"
    elif "test" in cmd_str or "pytest" in cmd_str or "cargo" in cmd_str:
        cat = "TDD / Test Verification"
    elif "git status" in cmd_str or "git diff" in cmd_str or "git branch" in cmd_str:
        cat = "Routine Git Lifecycle (git status, diff)"
    elif "identical consecutive" in err or "cyclic" in err:
        cat = "Genuine Runaway Loops / Repeating Thrashing"
    else:
        # Check sliding window
        if tool == "view_file":
            cat = "Teamwork Liveness / Heartbeat (progress.md)" if "progress" in target_str else "Repeated File Reading"
        elif tool == "run_command":
            cat = "Repeated Command Execution"
            
    if cat not in categories:
        categories[cat] = []
    categories[cat].append((sid, step, tool, cmd_str or target_str or action_str, err[:80]))

print("\n=== DENIAL BREAKDOWN BY WORKFLOW CATEGORY ===")
for cat, items in categories.items():
    print(f"\nCategory: {cat} (N={len(items)})")
    for it in items[:5]:
        print(f"  [{it[0][:8]} step {it[1]}] {it[2]}: {it[3][:60]} -> {it[4]}")
