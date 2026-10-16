import sqlite3

conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()

# Get all post-prototype sessions > 200 steps
c.execute('''
SELECT 
    session_id, total_steps, tool_call_count, tool_error_count, 
    intervention_count, has_errors, duration_seconds, workspace_path
FROM sessions
WHERE start_time >= '2026-10-02' AND total_steps > 200
ORDER BY total_steps DESC
''')

all_gt200 = c.fetchall()
print(f"Total sessions > 200 steps: {len(all_gt200)}")

clean_gt200 = [s for s in all_gt200 if s[5] == 0]
failed_gt200 = [s for s in all_gt200 if s[5] == 1]

print(f"Clean sessions > 200 steps (has_errors=0): {len(clean_gt200)} ({len(clean_gt200)/len(all_gt200)*100:.1f}%)")
print(f"Failed sessions > 200 steps (has_errors=1): {len(failed_gt200)} ({len(failed_gt200)/len(all_gt200)*100:.1f}%)")

# Let's compare metrics between clean and failed
def analyze_cohort(cohort, name):
    sids = [s[0] for s in cohort]
    if not sids:
        print(f"Cohort {name} is empty")
        return
    placeholders = ','.join(['?'] * len(sids))
    
    # 1. Status polling
    c.execute(f'''
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND tool_name = 'manage_task'
          AND arguments_json LIKE '%"status"%'
    ''', sids)
    status_polls, status_sess = c.fetchone()
    
    # 2. Task log reads
    c.execute(f'''
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND (
            (tool_name = 'view_file' AND (target_path LIKE '%/tasks/task-%.log' OR arguments_json LIKE '%/tasks/task-%.log'))
            OR (tool_name = 'run_command' AND (command_line LIKE '%/tasks/task-%.log' OR command_line LIKE '%tasks/task-%.log'))
          )
    ''', sids)
    log_reads, log_sess = c.fetchone()
    
    # 3. Anti-loop denials
    c.execute(f'''
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND error_snippet LIKE '%denied by pre-tool hook%'
    ''', sids)
    denials, denial_sess = c.fetchone()
    
    # 4. Replace file content failures
    c.execute(f'''
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND tool_name = 'replace_file_content'
          AND status IN ('ERROR', 'FAILED')
    ''', sids)
    edit_fails, edit_sess = c.fetchone()
    
    # 5. Total tool calls & errors
    tot_tools = sum(s[2] for s in cohort)
    tot_errors = sum(s[3] for s in cohort)
    tot_steps = sum(s[1] for s in cohort)
    avg_steps = tot_steps / len(cohort)
    avg_interv = sum(s[4] for s in cohort) / len(cohort)
    avg_dur = sum(s[6] for s in cohort) / len(cohort) / 60.0
    
    print(f"\n--- Cohort: {name} (N={len(cohort)}) ---")
    print(f"Avg steps: {avg_steps:.1f} | Avg duration: {avg_dur:.1f}m | Avg interventions: {avg_interv:.2f}")
    print(f"Total tools: {tot_tools} | Total errors: {tot_errors}")
    print(f"Status polls: {status_polls} across {status_sess} sessions ({status_polls/len(cohort):.2f}/sess)")
    print(f"Task log reads: {log_reads} across {log_sess} sessions ({log_reads/len(cohort):.2f}/sess)")
    print(f"Anti-loop denials: {denials} across {denial_sess} sessions ({denials/len(cohort):.2f}/sess)")
    print(f"Edit failures: {edit_fails} across {edit_sess} sessions ({edit_fails/len(cohort):.2f}/sess)")

analyze_cohort(clean_gt200, "Clean >200 Steps")
analyze_cohort(failed_gt200, "Failed >200 Steps")
