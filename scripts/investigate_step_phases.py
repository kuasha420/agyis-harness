import sqlite3

conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()

c.execute('''
SELECT 
    CASE
        WHEN tc.step_index < 50 THEN '1. Steps 0-49'
        WHEN tc.step_index BETWEEN 50 AND 99 THEN '2. Steps 50-99'
        WHEN tc.step_index BETWEEN 100 AND 199 THEN '3. Steps 100-199'
        WHEN tc.step_index BETWEEN 200 AND 399 THEN '4. Steps 200-399'
        ELSE '5. Steps 400+'
    END as step_phase,
    count(*) as total_calls,
    sum(case when tc.status in ('ERROR', 'FAILED') then 1 else 0 end) as errors,
    sum(case when tc.tool_name = 'replace_file_content' and tc.status in ('ERROR', 'FAILED') then 1 else 0 end) as edit_errors,
    sum(case when tc.error_snippet like '%cortex tool%' or tc.error_snippet like '%missing properties%' or tc.error_snippet like '%missing property%' then 1 else 0 end) as schema_corruptions,
    sum(case when tc.error_snippet like '%denied by pre-tool hook%' then 1 else 0 end) as hook_denials
FROM tool_calls tc
JOIN sessions s ON tc.session_id = s.session_id
WHERE s.start_time >= '2026-10-02'
GROUP BY step_phase
ORDER BY step_phase
''')

header = "%-18s | %-12s | %-8s | %-8s | %-10s | %-12s | %-12s" % (
    "Step Phase", "Total Calls", "Errors", "Err %", "Edit Err", "Schema Corr", "Hook Denials"
)
print(header)
print('-'*90)
for r in c.fetchall():
    pct = r[2]/r[1]*100 if r[1] else 0
    row = "%-18s | %-12s | %-8s | %-7.2f%% | %-10s | %-12s | %-12s" % (
        r[0], r[1], r[2], pct, r[3], r[4], r[5]
    )
    print(row)
