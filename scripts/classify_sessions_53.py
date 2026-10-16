import sqlite3
import json

conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()

# Get all 53 sessions with polluted calls
c.execute('''
SELECT DISTINCT s.session_id, s.start_time, s.workspace_path, s.total_steps
FROM tool_calls tc
JOIN sessions s ON tc.session_id = s.session_id
WHERE tc.tool_name = 'run_command'
  AND s.start_time >= '2026-10-02'
  AND (
      tc.command_line LIKE '%harness.cli%'
      OR tc.command_line LIKE '%agyis test%'
      OR tc.command_line LIKE '%./agyis test%'
      OR tc.command_line LIKE '%agyis doctor%'
      OR tc.command_line LIKE '%./agyis doctor%'
      OR tc.command_line LIKE '%python3 -m unittest discover -s tests -v%'
      OR tc.command_line LIKE '%python3 -m harness%'
  )
  AND json_extract(tc.arguments_json, '$.Cwd') NOT LIKE '%psl-agy-harness%'
  AND json_extract(tc.arguments_json, '$.Cwd') NOT LIKE '%agyis-harness%'
  AND json_extract(tc.arguments_json, '$.Cwd') NOT LIKE '%subagent-Stage-2-Executioner%'
  AND (json_extract(tc.arguments_json, '$.Cwd') != '"/home[WORKSPACE_ROOT]"' OR s.workspace_path != '4eacf503-ea78-4551-aac9-ac9878ecd20a')
ORDER BY s.start_time
''')

sessions = c.fetchall()

fleet_onboarding_sessions = []
user_commanded_governance = []
unprompted_invariant_leaks = []

for sid, start, ws, steps in sessions:
    c.execute('SELECT prompt_text FROM user_interventions WHERE session_id = ? ORDER BY step_index', (sid,))
    prompts = c.fetchall()
    all_prompts_text = " ".join([p[0] for p in prompts if p[0]])
    
    # Check tool calls
    c.execute('''
        SELECT step_index, command_line, json_extract(arguments_json, '$.Cwd')
        FROM tool_calls
        WHERE session_id = ? AND (
            command_line LIKE '%harness.cli%'
            OR command_line LIKE '%agyis test%'
            OR command_line LIKE '%./agyis test%'
            OR command_line LIKE '%agyis doctor%'
            OR command_line LIKE '%./agyis doctor%'
            OR command_line LIKE '%python3 -m unittest discover -s tests -v%'
            OR command_line LIKE '%python3 -m harness%'
        )
        AND json_extract(arguments_json, '$.Cwd') NOT LIKE '%psl-agy-harness%'
        AND json_extract(arguments_json, '$.Cwd') NOT LIKE '%agyis-harness%'
    ''', (sid,))
    calls = c.fetchall()
    cwds = set(cl[2] for cl in calls if cl[2])
    
    # Classification logic
    is_fleet = False
    if len(cwds) > 1 or 'onboard' in all_prompts_text.lower() or 'fleet' in all_prompts_text.lower() or 'wave 1' in all_prompts_text.lower():
        is_fleet = True
    elif start >= '2026-10-13T18:00:00' and start <= '2026-10-14T20:00:00' and any('agyis doctor' in cl[1] for cl in calls) and not any('harness.cli test' in cl[1] for cl in calls):
        # Wave 1 / Tier 1 / PR feedback sweeps
        is_fleet = True
        
    if is_fleet:
        fleet_onboarding_sessions.append((sid, start, len(cwds), len(calls), list(cwds)[:3]))
    elif 'mi34-ultra' in sid or 'f5f3aa79' in sid or '6e5ecfb1' in sid:
        user_commanded_governance.append((sid, start, len(cwds), len(calls), list(cwds)[:3]))
    else:
        unprompted_invariant_leaks.append((sid, start, len(cwds), len(calls), list(cwds)[:3]))

print(f"Fleet Onboarding Sessions: {len(fleet_onboarding_sessions)}")
print(f"User Commanded Governance Sessions: {len(user_commanded_governance)}")
print(f"Unprompted Invariant Leak Sessions: {len(unprompted_invariant_leaks)}")

print("\n--- SAMPLE UNPROMPTED LEAK SESSIONS ---")
for s in unprompted_invariant_leaks[:10]:
    print(f"ID: {s[0][:8]} | Date: {s[1][:10]} | Calls: {s[3]} | CWDs: {s[4]}")
