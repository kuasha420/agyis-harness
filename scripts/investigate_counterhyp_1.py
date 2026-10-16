import sqlite3
import json

sessions = [
    ("purrmission", "fbd37e82-336b-447d-9be7-0c39859df5be"),
    ("mi34-ultra", "f5f3aa79-24d2-4547-b5de-5c3dac5237df"),
    ("knot-mesh", "2a52173f-8768-47df-959c-39076213aa11"),
]

for name, sid in sessions:
    print(f"\n=======================================================")
    print(f"SESSION: {name} ({sid})")
    print(f"=======================================================")
    conv_path = f"/home/kuasha/.gemini/antigravity/conversations/{sid}.db"
    try:
        conn = sqlite3.connect(conv_path)
        c = conn.cursor()
        c.execute("SELECT idx, role, step_type, substr(content, 1, 500) FROM steps WHERE role = 'user' OR step_type LIKE '%user%' ORDER BY idx")
        rows = c.fetchall()
        print(f"User steps count: {len(rows)}")
        for r in rows:
            print(f"--- Step {r[0]} | role: {r[1]} | type: {r[2]} ---")
            print(r[3])
    except Exception as e:
        print(f"Error reading conv db: {e}")

    # Check telemetry tool calls with harness / doctor / test
    conn_t = sqlite3.connect("data/telemetry.db")
    ct = conn_t.cursor()
    ct.execute("""
        SELECT step_index, tool_name, command_line, json_extract(arguments_json, '$.Cwd'), exit_code, status
        FROM tool_calls
        WHERE session_id = ? AND (
            command_line LIKE '%harness%' OR
            command_line LIKE '%agyis%' OR
            command_line LIKE '%unittest%'
        )
        ORDER BY step_index
    """, (sid,))
    t_rows = ct.fetchall()
    print(f"\nHarness-related tool calls ({len(t_rows)}):")
    for tr in t_rows:
        print(f"Step {tr[0]}: {tr[1]} | cmd: {tr[2]} | cwd: {tr[3]} | ec: {tr[4]}")
