# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Empirical benchmark suite for testing model reasoning accuracy, latency, and thinking tokens
across Gemini 3.8 Flash reasoning effort levels (low, medium, high).
"""

import json
import subprocess
import time
from typing import Any, Dict, List

BENCHMARK_TASKS = [
    {
        "id": "logic_puzzle",
        "name": "Knight/Knave Multi-Constraint Deduction",
        "prompt": (
            "Three people (Alice, Bob, Carol) each either always tell the truth or always lie.\n"
            "Alice says: 'Bob is a liar.'\n"
            "Bob says: 'Carol and I are the same type (both truth-tellers or both liars).'\n"
            "Carol says: 'Alice is a liar.'\n"
            "Deduce who is telling the truth and who is lying. "
            "Return JSON ONLY with keys: 'alice' ('truth'|'liar'), 'bob' ('truth'|'liar'), 'carol' ('truth'|'liar'), and 'explanation'."
        ),
        "evaluator": lambda res: (
            res.get("alice") == "liar"
            and res.get("bob") == "truth"
            and res.get("carol") == "truth"
        ),
        "ground_truth": "alice=liar, bob=truth, carol=truth"
    },
    {
        "id": "mutable_default",
        "name": "Python Mutable Default Argument & State Simulation",
        "prompt": (
            "Consider this Python code:\n"
            "```python\n"
            "def process_items(items, default_cache={}):\n"
            "    results = []\n"
            "    for item in items:\n"
            "        if item in default_cache:\n"
            "            results.append(default_cache[item])\n"
            "        else:\n"
            "            default_cache[item] = len(default_cache)\n"
            "            results.append(default_cache[item])\n"
            "    return results\n"
            "\n"
            "r1 = process_items(['a', 'b', 'a'])\n"
            "r2 = process_items(['c', 'b', 'd'])\n"
            "```\n"
            "What are the exact values of r1 and r2?\n"
            "Return JSON ONLY with keys: 'r1' (list of ints), 'r2' (list of ints), and 'explanation'."
        ),
        "evaluator": lambda res: (
            res.get("r1") == [0, 1, 0]
            and res.get("r2") == [2, 1, 3]
        ),
        "ground_truth": "r1=[0, 1, 0], r2=[2, 1, 3]"
    },
    {
        "id": "conditional_prob",
        "name": "Conditional Probability (Socks Problem)",
        "prompt": (
            "A drawer contains 3 red socks, 4 blue socks, and 5 green socks (12 socks total).\n"
            "You draw 2 socks at random without replacement.\n"
            "Given that at least one of the drawn socks is red, what is the exact probability that both socks are red?\n"
            "Return JSON ONLY with key 'probability' formatted as an irreducible fraction string 'p/q' (e.g. '1/2') and 'explanation'."
        ),
        "evaluator": lambda res: (
            str(res.get("probability", "")).strip().replace(" ", "") == "1/10"
        ),
        "ground_truth": "1/10"
    },
    {
        "id": "distributed_causality",
        "name": "Distributed Actor FIFO vs Causal Ordering",
        "prompt": (
            "In an actor-model distributed system with reliable FIFO point-to-point channels between each pair of actors:\n"
            "1. Actor A sends message M1 to Actor B, and then sends message M2 to Actor C.\n"
            "2. Actor C, upon receiving M2, immediately sends message M3 to Actor B.\n"
            "Can message M3 arrive at Actor B before message M1 arrives at Actor B?\n"
            "Return JSON ONLY with key 'can_m3_arrive_before_m1' (boolean: true or false) and 'explanation'."
        ),
        "evaluator": lambda res: (
            res.get("can_m3_arrive_before_m1") is True
        ),
        "ground_truth": "true (point-to-point FIFO does not guarantee causal ordering across triangle)"
    }
]

TIERS = [
    {"model": "gemini-3.8-flash-low", "effort": "low"},
    {"model": "gemini-3.8-flash-medium", "effort": "medium"},
    {"model": "gemini-3.8-flash-high", "effort": "high"}
]

def run_probe(model: str, effort: str, prompt: str) -> Dict[str, Any]:
    cmd = [
        "agy",
        "--model", model,
        "--effort", effort,
        "--output-format", "json",
        "--print", prompt
    ]
    start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    wall_duration = time.time() - start

    if proc.returncode != 0:
        return {
            "error": proc.stderr or proc.stdout,
            "wall_duration": wall_duration
        }

    try:
        data = json.loads(proc.stdout)
        resp_text = data.get("response", "")
        clean_text = resp_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        parsed_json = json.loads(clean_text)
        return {
            "parsed": parsed_json,
            "raw_response": resp_text,
            "duration_seconds": data.get("duration_seconds", wall_duration),
            "usage": data.get("usage", {}),
            "error": None
        }
    except Exception as e:
        return {
            "error": f"JSON parse error: {e}",
            "raw_stdout": proc.stdout,
            "wall_duration": wall_duration
        }

def run_all():
    results = {}
    for tier in TIERS:
        tier_key = f"{tier['model']} ({tier['effort']})"
        print(f"\n=======================================================")
        print(f"BENCHMARKING: {tier_key}")
        print(f"=======================================================")
        results[tier_key] = []
        for task in BENCHMARK_TASKS:
            print(f"-> Running Task: {task['name']}...", flush=True)
            res = run_probe(tier["model"], tier["effort"], task["prompt"])
            passed = False
            parsed = res.get("parsed")
            if parsed and task["evaluator"](parsed):
                passed = True

            usage = res.get("usage", {})
            thinking = usage.get("thinking_tokens", 0)
            duration = res.get("duration_seconds", res.get("wall_duration", 0))

            print(f"   Result: {'PASS' if passed else 'FAIL'} | Thinking: {thinking} toks | Latency: {duration:.2f}s", flush=True)
            results[tier_key].append({
                "task_id": task["id"],
                "task_name": task["name"],
                "passed": passed,
                "parsed": parsed,
                "thinking_tokens": thinking,
                "duration_seconds": duration,
                "ground_truth": task["ground_truth"],
                "error": res.get("error")
            })

    print("\n\n" + "="*80)
    print("FINAL ACCURACY & PERFORMANCE MATRIX")
    print("="*80)
    print(f"{'Tier':<30} | {'Passed':<8} | {'Accuracy':<10} | {'Avg Thinking':<14} | {'Avg Latency'}")
    print("-" * 80)
    for tier_key, tasks in results.items():
        total = len(tasks)
        passed = sum(1 for t in tasks if t["passed"])
        acc = (passed / total) * 100
        avg_thinking = sum(t["thinking_tokens"] for t in tasks) / total
        avg_lat = sum(t["duration_seconds"] for t in tasks) / total
        print(f"{tier_key:<30} | {f'{passed}/{total}':<8} | {f'{acc:.1f}%':<10} | {f'{avg_thinking:.1f}':<14} | {avg_lat:.2f}s")

    with open("data/reasoning_benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved detailed results to data/reasoning_benchmark_results.json")

if __name__ == "__main__":
    run_all()
