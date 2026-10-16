import sqlite3
import json

conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()

c.execute('''
SELECT 
    tc.session_id, tc.step_index, tc.tool_name, tc.command_line, tc.arguments_json, tc.error_snippet
FROM tool_calls tc
JOIN sessions s ON tc.session_id = s.session_id
WHERE s.start_time >= '2026-10-02'
  AND tc.error_snippet LIKE '%denied by pre-tool hook%'
ORDER BY s.start_time, tc.session_id, tc.step_index
''')

denials = c.fetchall()

sample_indices = [0, 5, 15, 25, 35, 45, 55]

for idx in sample_indices:
    if idx >= len(denials):
        continue
    sid, step, tool, cmd, args_json, err = denials[idx]
    args = json.loads(args_json) if args_json else {}
    target = cmd or args.get("AbsolutePath") or args.get("Action")
    print(f"\n=======================================================")
    print(f"CASE {idx}: Session {sid[:8]} Step {step} | Tool: {tool}")
    print(f"Denied Target: {target}")
    print(f"Error: {err[:120]}")
    print(f"Subsequent 3 calls:")
    
    c.execute('''
        SELECT step_index, tool_name, command_line, arguments_json, status
        FROM tool_calls
        WHERE session_id = ? AND step_index > ?
        ORDER BY step_index
        LIMIT 3
    ''', (sid, step))
    for r in c.fetchall():
        r_args = json.loads(r[3]) if r[3] else {}
        r_target = r[2] or r_args.get("AbsolutePath") or r_args.get("Action") or r_args.get("CommandLine")
        print(f"  Step {r[0]}: {r[1]} -> {str(r_target)[:80]} (status: {r[4]})")
