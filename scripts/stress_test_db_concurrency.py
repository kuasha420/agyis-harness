#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Empirical SQLite Concurrency Stress Test Harness.

Verifies:
1. Multi-threaded read/write contention with get_db_connection()
2. Multi-process read/write contention across OS process boundaries
3. Non-blocking reader snapshot isolation during active writer transactions
4. Synchronized writer burst serialization via busy_timeout
5. Zero 'sqlite3.OperationalError: database is locked' exceptions under all contention regimes
6. Database integrity check and pragma invariants (WAL, busy_timeout, normal synchronous, foreign_keys)
"""

import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.telemetry.db import get_db_connection
from harness.telemetry.schema import init_db


def scenario_1_multithreaded_contention(db_file: Path) -> Dict[str, Any]:
    """Test 10 concurrent threads (5 writers, 5 readers) performing simultaneous ops."""
    print("  [Scenario 1] Multi-Threaded Read/Write Contention (10 threads)...")
    errors: List[str] = []
    lock_errors: List[str] = []
    start_time = time.perf_counter()

    num_writers = 5
    writes_per_thread = 40
    num_readers = 5
    reads_per_thread = 80

    def writer_worker(thread_id: int):
        for i in range(writes_per_thread):
            session_id = f"thread-w{thread_id}-s{i}"
            try:
                conn = get_db_connection(db_file, timeout=30.0)
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO sessions (
                            session_id, start_time, end_time, duration_seconds, total_steps,
                            model, workspace_path, transcript_path, file_size_bytes, has_errors,
                            tool_call_count, tool_error_count, intervention_count,
                            origin_developer, remote_synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id, "2026-10-15T00:00:00Z", "2026-10-15T00:05:00Z",
                            300.0, 3, "gemini-2.5-pro", "/workspace", "/transcripts/1.jsonl",
                            1024, 0, 2, 0, 0, "local", None
                        ),
                    )
                    for step_idx in range(3):
                        cur.execute(
                            """
                            INSERT INTO steps (session_id, step_index, step_type, status)
                            VALUES (?, ?, ?, ?)
                            """,
                            (session_id, step_idx, "MODEL_OUTPUT", "SUCCESS"),
                        )
                    for tool_idx in range(2):
                        cur.execute(
                            """
                            INSERT INTO tool_calls (session_id, step_index, tool_name, status)
                            VALUES (?, ?, ?, ?)
                            """,
                            (session_id, tool_idx, f"tool_{tool_idx}", "SUCCESS"),
                        )
                    conn.commit()
                finally:
                    conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    lock_errors.append(f"Writer thread {thread_id} op {i}: {e}")
                errors.append(f"Writer thread {thread_id} op {i}: {e}")
            except Exception as e:
                errors.append(f"Writer thread {thread_id} op {i}: {e}")

    def reader_worker(thread_id: int):
        for i in range(reads_per_thread):
            try:
                conn = get_db_connection(db_file, timeout=30.0)
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT count(*), max(duration_seconds) FROM sessions")
                    _ = cur.fetchone()
                    cur.execute("SELECT count(*) FROM tool_calls WHERE status = 'SUCCESS'")
                    _ = cur.fetchone()
                finally:
                    conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    lock_errors.append(f"Reader thread {thread_id} op {i}: {e}")
                errors.append(f"Reader thread {thread_id} op {i}: {e}")
            except Exception as e:
                errors.append(f"Reader thread {thread_id} op {i}: {e}")

    threads = []
    for t_id in range(num_writers):
        threads.append(threading.Thread(target=writer_worker, args=(t_id,)))
    for t_id in range(num_readers):
        threads.append(threading.Thread(target=reader_worker, args=(t_id,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.perf_counter() - start_time

    # Verify counts
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sessions")
        session_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM steps")
        step_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM tool_calls")
        tool_count = cur.fetchone()[0]
    finally:
        conn.close()

    expected_sessions = num_writers * writes_per_thread
    expected_steps = expected_sessions * 3
    expected_tools = expected_sessions * 2

    success = (
        len(errors) == 0
        and len(lock_errors) == 0
        and session_count == expected_sessions
        and step_count == expected_steps
        and tool_count == expected_tools
    )

    return {
        "name": "Multi-Threaded Contention",
        "writers": num_writers,
        "readers": num_readers,
        "total_writes": expected_sessions,
        "total_reads": num_readers * reads_per_thread,
        "duration_seconds": round(duration, 4),
        "errors_count": len(errors),
        "lock_errors_count": len(lock_errors),
        "verified_counts": {
            "sessions": session_count,
            "steps": step_count,
            "tool_calls": tool_count,
        },
        "success": success,
    }


def _proc_writer(proc_id: int, db_path: str, num_writes: int, error_queue: mp.Queue):
    """Process worker function for writing."""
    for i in range(num_writes):
        session_id = f"proc-w{proc_id}-s{i}"
        try:
            conn = get_db_connection(db_path, timeout=30.0)
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count,
                        origin_developer, remote_synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id, "2026-10-15T00:00:00Z", "2026-10-15T00:05:00Z",
                        300.0, 3, "gemini-2.5-pro", "/workspace", "/transcripts/1.jsonl",
                        1024, 0, 2, 0, 0, "local", None
                    ),
                )
                for step_idx in range(3):
                    cur.execute(
                        """
                        INSERT INTO steps (session_id, step_index, step_type, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, step_idx, "MODEL_OUTPUT", "SUCCESS"),
                    )
                for tool_idx in range(2):
                    cur.execute(
                        """
                        INSERT INTO tool_calls (session_id, step_index, tool_name, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, tool_idx, f"tool_{tool_idx}", "SUCCESS"),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            error_queue.put((f"Process Writer {proc_id} op {i}", str(e), type(e).__name__))


def _proc_reader(proc_id: int, db_path: str, num_reads: int, error_queue: mp.Queue):
    """Process worker function for reading."""
    for i in range(num_reads):
        try:
            conn = get_db_connection(db_path, timeout=30.0)
            try:
                cur = conn.cursor()
                cur.execute("SELECT count(*), max(duration_seconds) FROM sessions")
                _ = cur.fetchone()
                cur.execute("SELECT count(*) FROM tool_calls WHERE status = 'SUCCESS'")
                _ = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:
            error_queue.put((f"Process Reader {proc_id} op {i}", str(e), type(e).__name__))


def scenario_2_multiprocess_contention(db_file: Path, initial_sessions: int) -> Dict[str, Any]:
    """Test concurrent OS processes (3 writers, 3 readers) writing/reading simultaneously."""
    print("  [Scenario 2] Multi-Process Read/Write Contention (6 OS processes)...")
    error_queue: mp.Queue = mp.Queue()
    start_time = time.perf_counter()

    num_writers = 3
    writes_per_proc = 30
    num_readers = 3
    reads_per_proc = 60

    processes = []
    for p_id in range(num_writers):
        p = mp.Process(target=_proc_writer, args=(p_id, str(db_file), writes_per_proc, error_queue))
        processes.append(p)

    for p_id in range(num_readers):
        p = mp.Process(target=_proc_reader, args=(p_id, str(db_file), reads_per_proc, error_queue))
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join()

    duration = time.perf_counter() - start_time

    # Drain error queue
    all_errors = []
    lock_errors = []
    while not error_queue.empty():
        item = error_queue.get()
        all_errors.append(item)
        if "locked" in item[1].lower() or "busy" in item[1].lower():
            lock_errors.append(item)

    # Verify counts
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sessions")
        session_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM steps")
        step_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM tool_calls")
        tool_count = cur.fetchone()[0]
    finally:
        conn.close()

    expected_new_sessions = num_writers * writes_per_proc
    total_expected_sessions = initial_sessions + expected_new_sessions

    success = (
        len(all_errors) == 0
        and len(lock_errors) == 0
        and session_count == total_expected_sessions
    )

    return {
        "name": "Multi-Process Contention",
        "writer_processes": num_writers,
        "reader_processes": num_readers,
        "writes_per_process": writes_per_proc,
        "reads_per_process": reads_per_proc,
        "duration_seconds": round(duration, 4),
        "errors_count": len(all_errors),
        "lock_errors_count": len(lock_errors),
        "verified_counts": {
            "total_sessions": session_count,
            "total_steps": step_count,
            "total_tool_calls": tool_count,
        },
        "success": success,
    }


def scenario_3_snapshot_isolation_during_active_writer(db_file: Path) -> Dict[str, Any]:
    """Verify readers are not blocked by an active, sleeping writer transaction in WAL mode."""
    print("  [Scenario 3] Reader Snapshot Isolation During Active Writer...")
    writer_ready = threading.Event()
    writer_sleep_done = threading.Event()
    reader_latencies: List[float] = []
    reader_errors: List[str] = []

    def long_writer():
        conn = get_db_connection(db_file, timeout=30.0)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, start_time, end_time, duration_seconds, total_steps,
                    model, workspace_path, transcript_path, file_size_bytes, has_errors,
                    tool_call_count, tool_error_count, intervention_count,
                    origin_developer, remote_synced_at
                ) VALUES ('isolated-session-long', '2026-10-15T01:00:00Z', NULL, 10.0, 0, 'gemini', '/p', '/t', 10, 0, 0, 0, 0, 'local', NULL)
                """
            )
            writer_ready.set()
            # Sleep 200ms while holding the write lock
            time.sleep(0.2)
            conn.commit()
            writer_sleep_done.set()
        finally:
            conn.close()

    def concurrent_reader():
        writer_ready.wait(timeout=5.0)
        t0 = time.perf_counter()
        try:
            conn = get_db_connection(db_file, timeout=30.0)
            try:
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM sessions")
                _ = cur.fetchone()
            finally:
                conn.close()
            elapsed = time.perf_counter() - t0
            reader_latencies.append(elapsed)
        except Exception as e:
            reader_errors.append(str(e))

    w_thread = threading.Thread(target=long_writer)
    r_threads = [threading.Thread(target=concurrent_reader) for _ in range(5)]

    w_thread.start()
    for r in r_threads:
        r.start()

    for r in r_threads:
        r.join()
    w_thread.join()

    # The readers should execute almost instantaneously (< 0.05s) despite writer sleeping 0.20s
    max_reader_latency = max(reader_latencies) if reader_latencies else 999.0
    avg_reader_latency = sum(reader_latencies) / len(reader_latencies) if reader_latencies else 999.0

    # Reader must NOT have been blocked for the 200ms
    is_non_blocking = max_reader_latency < 0.15

    success = (
        len(reader_errors) == 0
        and is_non_blocking
    )

    return {
        "name": "Reader Snapshot Isolation During Active Writer",
        "readers_tested": len(r_threads),
        "reader_errors_count": len(reader_errors),
        "avg_reader_latency_seconds": round(avg_reader_latency, 6),
        "max_reader_latency_seconds": round(max_reader_latency, 6),
        "writer_hold_duration_seconds": 0.2,
        "non_blocking_verified": is_non_blocking,
        "success": success,
    }


def scenario_4_synchronized_writer_burst(db_file: Path) -> Dict[str, Any]:
    """Test 8 writers attempting simultaneous write at the exact same microsecond."""
    print("  [Scenario 4] Synchronized Writer Burst Serialization (8 concurrent writers)...")
    num_writers = 8
    barrier = threading.Barrier(num_writers)
    burst_errors: List[str] = []
    lock_errors: List[str] = []
    start_time = time.perf_counter()

    def burst_writer(w_id: int):
        barrier.wait()  # Synchronize all threads to start at identical instant
        session_id = f"burst-session-{w_id}"
        try:
            conn = get_db_connection(db_file, timeout=30.0)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count,
                        origin_developer, remote_synced_at
                    ) VALUES (?, '2026-10-15T02:00:00Z', NULL, 15.0, 0, 'gemini', '/p', '/t', 10, 0, 0, 0, 0, 'local', NULL)
                    """,
                    (session_id,),
                )
                # Tiny simulated commit overhead
                time.sleep(0.005)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                lock_errors.append(f"Burst writer {w_id}: {e}")
            burst_errors.append(f"Burst writer {w_id}: {e}")
        except Exception as e:
            burst_errors.append(f"Burst writer {w_id}: {e}")

    threads = [threading.Thread(target=burst_writer, args=(i,)) for i in range(num_writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.perf_counter() - start_time

    # Verify all burst sessions exist
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sessions WHERE session_id LIKE 'burst-session-%'")
        burst_count = cur.fetchone()[0]
    finally:
        conn.close()

    success = (
        len(burst_errors) == 0
        and len(lock_errors) == 0
        and burst_count == num_writers
    )

    return {
        "name": "Synchronized Writer Burst Serialization",
        "concurrent_writers": num_writers,
        "duration_seconds": round(duration, 4),
        "errors_count": len(burst_errors),
        "lock_errors_count": len(lock_errors),
        "burst_records_written": burst_count,
        "success": success,
    }


def scenario_5_database_invariants_and_integrity(db_file: Path) -> Dict[str, Any]:
    """Verify SQLite pragmas and table integrity after all stress scenarios."""
    print("  [Scenario 5] Database Invariants & Integrity Check...")
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode")
        journal_mode = cur.fetchone()[0].lower()

        cur.execute("PRAGMA busy_timeout")
        busy_timeout = cur.fetchone()[0]

        cur.execute("PRAGMA synchronous")
        synchronous = cur.fetchone()[0]

        cur.execute("PRAGMA foreign_keys")
        foreign_keys = cur.fetchone()[0]

        cur.execute("PRAGMA integrity_check")
        integrity = cur.fetchone()[0].lower()

        cur.execute("SELECT count(*) FROM sessions")
        total_sessions = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM steps")
        total_steps = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM tool_calls")
        total_tools = cur.fetchone()[0]
    finally:
        conn.close()

    wal_ok = (journal_mode == "wal")
    timeout_ok = (busy_timeout == 30000)
    sync_ok = (synchronous == 1)  # NORMAL
    fk_ok = (foreign_keys == 1)    # ON
    integrity_ok = (integrity == "ok")

    success = wal_ok and timeout_ok and sync_ok and fk_ok and integrity_ok

    return {
        "name": "Database Invariants & Integrity",
        "journal_mode": journal_mode,
        "journal_mode_wal": wal_ok,
        "busy_timeout_ms": busy_timeout,
        "busy_timeout_ok": timeout_ok,
        "synchronous_level": synchronous,
        "synchronous_normal": sync_ok,
        "foreign_keys_enabled": foreign_keys,
        "foreign_keys_ok": fk_ok,
        "integrity_check": integrity,
        "integrity_ok": integrity_ok,
        "final_counts": {
            "sessions": total_sessions,
            "steps": total_steps,
            "tool_calls": total_tools,
        },
        "success": success,
    }



def scenario_6_heavy_volume_burst(db_file: Path) -> Dict[str, Any]:
    """Test 20 concurrent threads (10 writers, 10 readers) performing 1,500 operations under heavy contention."""
    print("  [Scenario 6] Heavy Volume Contention Burst (20 threads, 1,500 operations)...")
    errors: List[str] = []
    lock_errors: List[str] = []
    start_time = time.perf_counter()

    num_writers = 10
    writes_per_thread = 50
    num_readers = 10
    reads_per_thread = 100

    def writer_worker(thread_id: int):
        for i in range(writes_per_thread):
            session_id = f"heavy-w{thread_id}-s{i}"
            try:
                conn = get_db_connection(db_file, timeout=30.0)
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO sessions (
                            session_id, start_time, end_time, duration_seconds, total_steps,
                            model, workspace_path, transcript_path, file_size_bytes, has_errors,
                            tool_call_count, tool_error_count, intervention_count,
                            origin_developer, remote_synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id, "2026-10-15T03:00:00Z", "2026-10-15T03:05:00Z",
                            300.0, 1, "gemini-2.5-pro", "/workspace", "/transcripts/h.jsonl",
                            2048, 0, 1, 0, 0, "heavy_tester", None
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    lock_errors.append(f"Heavy writer {thread_id} op {i}: {e}")
                errors.append(f"Heavy writer {thread_id} op {i}: {e}")
            except Exception as e:
                errors.append(f"Heavy writer {thread_id} op {i}: {e}")

    def reader_worker(thread_id: int):
        for i in range(reads_per_thread):
            try:
                conn = get_db_connection(db_file, timeout=30.0)
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT count(*) FROM sessions WHERE origin_developer = 'heavy_tester'")
                    _ = cur.fetchone()
                finally:
                    conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    lock_errors.append(f"Heavy reader {thread_id} op {i}: {e}")
                errors.append(f"Heavy reader {thread_id} op {i}: {e}")
            except Exception as e:
                errors.append(f"Heavy reader {thread_id} op {i}: {e}")

    threads = []
    for t_id in range(num_writers):
        threads.append(threading.Thread(target=writer_worker, args=(t_id,)))
    for t_id in range(num_readers):
        threads.append(threading.Thread(target=reader_worker, args=(t_id,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.perf_counter() - start_time

    # Verify count of heavy tester sessions
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sessions WHERE origin_developer = 'heavy_tester'")
        heavy_count = cur.fetchone()[0]
    finally:
        conn.close()

    expected_heavy = num_writers * writes_per_thread
    success = (
        len(errors) == 0
        and len(lock_errors) == 0
        and heavy_count == expected_heavy
    )

    return {
        "name": "Heavy Volume Contention Burst",
        "writers": num_writers,
        "readers": num_readers,
        "total_writes": expected_heavy,
        "total_reads": num_readers * reads_per_thread,
        "duration_seconds": round(duration, 4),
        "errors_count": len(errors),
        "lock_errors_count": len(lock_errors),
        "heavy_records_written": heavy_count,
        "success": success,
    }


def run_all_stress_tests() -> Dict[str, Any]:
    """Execute complete SQLite stress test suite in clean-room temporary directory."""
    print("=== PSL Empirical SQLite Concurrency Stress Test ===")
    overall_start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "stress_telemetry.db"

        # Initialize schema
        init_conn = get_db_connection(db_file)
        init_db(init_conn)
        init_conn.close()

        # Run scenarios
        s1 = scenario_1_multithreaded_contention(db_file)
        initial_sessions = s1["verified_counts"]["sessions"]

        s2 = scenario_2_multiprocess_contention(db_file, initial_sessions)
        s3 = scenario_3_snapshot_isolation_during_active_writer(db_file)
        s4 = scenario_4_synchronized_writer_burst(db_file)
        s6 = scenario_6_heavy_volume_burst(db_file)
        s5 = scenario_5_database_invariants_and_integrity(db_file)

    total_duration = time.perf_counter() - overall_start

    all_passed = all([
        s1["success"],
        s2["success"],
        s3["success"],
        s4["success"],
        s6["success"],
        s5["success"],
    ])

    total_lock_errors = (
        s1["lock_errors_count"]
        + s2["lock_errors_count"]
        + len(s3.get("reader_errors", []))
        + s4["lock_errors_count"]
        + s6["lock_errors_count"]
    )

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_duration_seconds": round(total_duration, 4),
        "overall_success": all_passed,
        "zero_lock_errors_guarantee": (total_lock_errors == 0),
        "total_lock_errors": total_lock_errors,
        "scenarios": [s1, s2, s3, s4, s6, s5],
    }

    print(f"\nStress Test Results Summary:")
    print(f"  Overall Success: {all_passed}")
    print(f"  Zero Lock Errors Asserted: {total_lock_errors == 0} (count: {total_lock_errors})")
    print(f"  Total Duration: {round(total_duration, 3)}s")

    return results


if __name__ == "__main__":
    results = run_all_stress_tests()
    out_file = REPO_ROOT / "scripts" / "stress_test_db_concurrency_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Detailed results written to {out_file}")
    if not results["overall_success"]:
        sys.exit(1)
    sys.exit(0)
