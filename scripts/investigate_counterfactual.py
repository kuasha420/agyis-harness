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

reactions = {
    "evasion_switch_tool": 0,      # tried to do same thing via run_command / different tool
    "stopped_and_waited": 0,       # stopped calling tools / waited
    "retried_same_command": 0,     # panicked / retried
    "switched_strategy": 0,        # pursued valid alternate subtask
    "user_intervened": 0           # user had to step in
}

for d in denials:
    sid, step, tool, cmd, args_json, err = d
    
    # Check next 3 tool calls in this session
    c.execute('''
        SELECT step_index, tool_name, command_line, arguments_json, status, error_snippet
        FROM tool_calls
        WHERE session_id = ? AND step_index > ?
        ORDER BY step_index
        LIMIT 3
    ''', (sid, step))
    next_calls = c.fetchall()
    
    # Check if user intervened in next 5 steps
    c.execute('''
        SELECT step_index, prompt_text
        FROM user_interventions
        WHERE session_id = ? AND step_index BETWEEN ? AND ?
    ''', (sid, step, step + 5))
    interv = c.fetchall()
    
    if interv:
        reactions["user_intervened"] += 1
    elif not next_calls:
        reactions["stopped_and_waited"] += 1
    else:
        first_next = next_calls[0]
        n_tool = first_next[1]
        n_cmd = first_next[2] or ""
        n_args = json.loads(first_next[3]) if first_next[3] else {}
        
        if tool == "view_file" and n_tool == "run_command" and ("cat" in n_cmd or "stat" in n_cmd or "head" in n_cmd):
            reactions["evasion_switch_tool"] += 1
        elif tool == "manage_task" and n_tool in ("view_file", "run_command") and "task" in (n_cmd or n_args.get("AbsolutePath", "")):
            reactions["evasion_switch_tool"] += 1
        elif n_tool == tool and (n_cmd == cmd or n_args.get("AbsolutePath") == json.loads(args_json or "{}").get("AbsolutePath")):
            reactions["retried_same_command"] += 1
        else:
            reactions["switched_strategy"] += 1

print("=== COUNTERFACTUAL AGENT REACTIONS TO ANTI-LOOP DENIALS ===")
for r, cnt in reactions.items():
    print(f"{r:<25}: {cnt} ({cnt/len(denials)*100:.1f}%)")
