#!/usr/bin/env python3
"""
Hermetic Unit and Contract Tests for Client-Side Redaction & Sanitization Engine (ADR-030).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import time
import unittest

from harness.telemetry.redaction import (
    anonymize_paths,
    sanitize_intervention,
    sanitize_tool_call,
    strip_secrets,
)


class TestSecretRedaction(unittest.TestCase):
    """Verifies strip_secrets across all credential formats and benign inputs."""

    def test_bearer_token_redaction(self):
        """Verifies Bearer tokens in headers and text are redacted."""
        samples = [
            ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token", "Bearer [REDACTED_SECRET]"),
            ("bearer ya29.a0AfH6SMB_dummy_gcp_access_token", "Bearer [REDACTED_SECRET]"),
            ("Authorization: Bearer my_secret_token_12345", "Authorization: Bearer [REDACTED_SECRET]"),
        ]
        for original, expected in samples:
            self.assertEqual(strip_secrets(original), expected)

    def test_github_token_redaction(self):
        """Verifies all GitHub token prefixes are replaced with [REDACTED_GITHUB_TOKEN]."""
        tokens = [
            "ghp_1234567890abcdef1234567890abcdef",
            "gho_dummyOAuthToken1234567890abcdef",
            "ghu_dummyUserToken1234567890abcdef",
            "ghs_dummyServerToken1234567890abcdef",
            "ghr_dummyRefreshToken1234567890abcdef",
            "github_pat_11AAAAAAA0000000000000_1234567890abcdef",
        ]
        for token in tokens:
            result = strip_secrets(f"curl -u user:{token} https://api.github.com")
            self.assertNotIn(token, result)
            self.assertIn("[REDACTED_GITHUB_TOKEN]", result)

    def test_aws_access_key_redaction(self):
        """Verifies AWS access keys (AKIA/ASIA) and secret access keys."""
        res_akia = strip_secrets("export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", res_akia)
        self.assertIn("[REDACTED_AWS_KEY]", res_akia)

        res_asia = strip_secrets("export AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE")
        self.assertNotIn("ASIAIOSFODNN7EXAMPLE", res_asia)
        self.assertIn("[REDACTED_AWS_KEY]", res_asia)

        res_sec = strip_secrets("aws_secret_access_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'")
        self.assertNotIn("wJalrXUtnFEMI", res_sec)
        self.assertEqual(res_sec, "aws_secret_access_key = '[REDACTED_SECRET]'")

    def test_api_keys_redaction(self):
        """Verifies OpenAI, Google AI, Slack, and generic API keys."""
        # OpenAI
        res_openai = strip_secrets("OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012mno345pqr678")
        self.assertNotIn("sk-proj-abc123def", res_openai)
        self.assertIn("[REDACTED_API_KEY]", res_openai)

        res_openai_legacy = strip_secrets("key=sk-abcdefghijklmnopqrstuvwxyz012345")
        self.assertNotIn("sk-abcdef", res_openai_legacy)
        self.assertIn("[REDACTED_API_KEY]", res_openai_legacy)

        # Google AI
        res_google = strip_secrets("GEMINI_KEY=AIzaSyD-abc123def456ghi789jkl012mno345pqr")
        self.assertNotIn("AIzaSyD-abc123def", res_google)
        self.assertIn("[REDACTED_API_KEY]", res_google)

        # Slack
        res_slack_b = strip_secrets("SLACK_BOT=xoxb-123456789012-1234567890123-dummytoken")
        self.assertNotIn("xoxb-12345", res_slack_b)
        self.assertIn("[REDACTED_API_KEY]", res_slack_b)

        res_slack_p = strip_secrets("SLACK_USER=xoxp-123456789012-1234567890123-dummytoken")
        self.assertNotIn("xoxp-12345", res_slack_p)
        self.assertIn("[REDACTED_API_KEY]", res_slack_p)

        # Generic key- prefix
        res_mailgun = strip_secrets("MAILGUN_KEY=key-abcdef0123456789abcdef0123456789")
        self.assertNotIn("key-abcdef0123", res_mailgun)
        self.assertIn("[REDACTED_API_KEY]", res_mailgun)

        # Assignments
        self.assertEqual(strip_secrets("api_key = abcdef1234567890"), "api_key = [REDACTED_API_KEY]")
        self.assertEqual(strip_secrets("api_key: 'abcdef1234567890'"), "api_key: '[REDACTED_API_KEY]'")
        self.assertEqual(strip_secrets("--api-key abcdef1234567890"), "--api-key [REDACTED_API_KEY]")
        self.assertEqual(strip_secrets("--api-key=abcdef1234567890"), "--api-key=[REDACTED_API_KEY]")

    def test_private_keys_redaction(self):
        """Verifies RSA, EC, OpenSSH, and standard PEM private key blocks."""
        rsa_pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0dummydatahere...\n"
            "-----END RSA PRIVATE KEY-----"
        )
        self.assertEqual(strip_secrets(rsa_pem), "[REDACTED_PRIVATE_KEY]")

        ec_pem = (
            "-----BEGIN EC PRIVATE KEY-----\n"
            "MHcCAQEEIdummydatahere...\n"
            "-----END EC PRIVATE KEY-----"
        )
        self.assertEqual(strip_secrets(ec_pem), "[REDACTED_PRIVATE_KEY]")

        ssh_pem = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNza-key-dummy...\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        self.assertEqual(strip_secrets(ssh_pem), "[REDACTED_PRIVATE_KEY]")

        generic_pem = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC6dummy...\n"
            "-----END PRIVATE KEY-----"
        )
        self.assertEqual(strip_secrets(generic_pem), "[REDACTED_PRIVATE_KEY]")

    def test_password_flags_and_urls(self):
        """Verifies CLI flags, config assignments, and URL credentials."""
        self.assertEqual(
            strip_secrets("psql --password secretpassword db"),
            "psql --password [REDACTED_PASSWORD] db",
        )
        self.assertEqual(
            strip_secrets("psql --password=secretpassword db"),
            "psql --password=[REDACTED_PASSWORD] db",
        )
        self.assertEqual(
            strip_secrets("password = 'mysecretpassword'"),
            "password = '[REDACTED_PASSWORD]'",
        )
        self.assertEqual(
            strip_secrets("passwd: \"mysecretpassword\""),
            "passwd: \"[REDACTED_PASSWORD]\"",
        )
        self.assertEqual(
            strip_secrets("postgres://user:super_secret@localhost:5432/mydb"),
            "postgres://user:[REDACTED_PASSWORD]@localhost:5432/mydb",
        )
        self.assertEqual(
            strip_secrets("mysql://root:secretpass@127.0.0.1:3306/db"),
            "mysql://root:[REDACTED_PASSWORD]@127.0.0.1:3306/db",
        )
        self.assertEqual(
            strip_secrets("redis://:myredispass@redis-host:6379/0"),
            "redis://:[REDACTED_PASSWORD]@redis-host:6379/0",
        )

    def test_authorization_headers(self):
        """Verifies Basic and Token authorization headers."""
        self.assertEqual(
            strip_secrets("Authorization: Basic dXNlcjpwYXNz"),
            "Authorization: Basic [REDACTED_SECRET]",
        )
        self.assertEqual(
            strip_secrets("Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"),
            "Authorization: Token [REDACTED_SECRET]",
        )
        self.assertEqual(
            strip_secrets("Authorization: secret_raw_token"),
            "Authorization: [REDACTED_SECRET]",
        )

    def test_generic_secrets(self):
        """Verifies generic secret assignments (client_secret, secret_key)."""
        self.assertEqual(
            strip_secrets("secret_key = 'abcdef1234567890'"),
            "secret_key = '[REDACTED_SECRET]'",
        )
        self.assertEqual(
            strip_secrets("client_secret: \"abcdef1234567890\""),
            "client_secret: \"[REDACTED_SECRET]\"",
        )

    def test_benign_inputs_not_corrupted(self):
        """Ensures benign code, paths, and commands are preserved without false positives."""
        benign_cases = [
            'git commit -m "fix: bug in login flow"',
            "def test_key():\n    return {'key': 'value'}",
            "for key, value in data.items(): pass",
            "def password_check(user): return True",
            "https://github.com/kuasha/psl-agy-harness",
            "postgres://localhost:5432/mydb",
            "python3 -m unittest discover -s tests -v",
            "password = None",
            'api_key = ""',
            "",
        ]
        for case in benign_cases:
            self.assertEqual(strip_secrets(case), case)


class TestPathAnonymization(unittest.TestCase):
    """Verifies anonymize_paths across workspace roots, home directories, and relative paths."""

    def test_workspace_root_anonymization(self):
        """Verifies workspace_root is replaced with [WORKSPACE_ROOT]."""
        ws = "/home/kuasha/Dev/psl-agy-harness"
        text = f"Editing file {ws}/harness/telemetry/redaction.py"
        expected = "Editing file [WORKSPACE_ROOT]/harness/telemetry/redaction.py"
        self.assertEqual(anonymize_paths(text, workspace_root=ws), expected)

    def test_user_home_anonymization(self):
        """Verifies user home paths (/home/<user> or /Users/<user>) are replaced with [USER_HOME]."""
        text_linux = "Logs written to /home/developer/.cache/psl/audit.log"
        expected_linux = "Logs written to [USER_HOME]/.cache/psl/audit.log"
        self.assertEqual(anonymize_paths(text_linux), expected_linux)

        text_mac = "Config stored at /Users/developer/Library/Application Support/app"
        expected_mac = "Config stored at [USER_HOME]/Library/Application Support/app"
        self.assertEqual(anonymize_paths(text_mac), expected_mac)

    def test_explicit_home_dir(self):
        """Verifies explicit home_dir parameter is respected."""
        text = "/custom/home/alice/secrets.txt"
        expected = "[USER_HOME]/secrets.txt"
        self.assertEqual(anonymize_paths(text, home_dir="/custom/home/alice"), expected)

    def test_workspace_inside_home_priority(self):
        """Verifies workspace_root is replaced first, before home directory scrubbing."""
        ws = "/home/kuasha/Dev/psl-agy-harness"
        text = f"{ws}/tests/test_redaction.py and /home/kuasha/.bashrc"
        expected = "[WORKSPACE_ROOT]/tests/test_redaction.py and [USER_HOME]/.bashrc"
        self.assertEqual(anonymize_paths(text, workspace_root=ws), expected)

    def test_relative_paths_preserved(self):
        """Verifies relative paths and standard repo structures remain unmodified."""
        relative_text = "python3 -m harness.cli test --path ./tests/test_redaction.py"
        self.assertEqual(
            anonymize_paths(relative_text, workspace_root="/workspace"),
            relative_text,
        )


class TestInterventionSanitization(unittest.TestCase):
    """Verifies sanitize_intervention across sanitize, omit, and metadata_only modes."""

    def test_sanitize_mode(self):
        """Verifies sanitize mode removes secrets and anonymizes workspace root."""
        prompt = (
            "Deploy using token ghp_1234567890abcdef1234567890abcdef "
            "at /home/kuasha/Dev/psl-agy-harness/deploy.sh"
        )
        ws = "/home/kuasha/Dev/psl-agy-harness"
        result = sanitize_intervention(prompt, mode="sanitize", workspace_root=ws)
        self.assertNotIn("ghp_", result)
        self.assertNotIn(ws, result)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", result)
        self.assertIn("[WORKSPACE_ROOT]/deploy.sh", result)

    def test_omit_mode(self):
        """Verifies omit mode discards prompt completely."""
        prompt = "Super sensitive operator instruction"
        self.assertEqual(sanitize_intervention(prompt, mode="omit"), "[PROMPT_OMITTED]")

    def test_metadata_only_mode(self):
        """Verifies metadata_only mode reports only character length."""
        prompt = "Create a database migration"
        expected = f"[PROMPT_REDACTED len={len(prompt)}]"
        self.assertEqual(sanitize_intervention(prompt, mode="metadata_only"), expected)

    def test_invalid_mode_raises(self):
        """Verifies invalid mode raises ValueError."""
        with self.assertRaises(ValueError):
            sanitize_intervention("Hello", mode="unsupported_mode")


class TestToolCallSanitization(unittest.TestCase):
    """Verifies sanitize_tool_call across payloads, JSON structures, and nesting."""

    def setUp(self):
        self.workspace_root = "/home/kuasha/Dev/psl-agy-harness"
        self.raw_tool_call = {
            "tool_name": "run_command",
            "call_id": "call_abc123",
            "command_line": (
                "curl -H 'Authorization: Bearer my_secret_token_123' "
                "postgres://user:dbpass@localhost:5432/telemetry"
            ),
            "arguments_snippet": "cmd: /home/kuasha/Dev/psl-agy-harness/run.sh --password adminpass",
            "error_snippet": "Error in /home/kuasha/Dev/psl-agy-harness/main.py: key-0123456789abcdef0123456789 rejected",
            "target_path": "/home/kuasha/Dev/psl-agy-harness/harness/cli.py",
            "arguments_json": json.dumps({
                "CommandLine": "export API_KEY=sk-proj-1234567890123456789012345",
                "TargetFile": "/home/kuasha/Dev/psl-agy-harness/tests/test_cli.py",
                "meta": {
                    "token": "ghp_1234567890abcdef1234567890abcdef",
                    "step": 42,
                    "active": True,
                },
            }),
            "nested_calls": [
                {
                    "tool_name": "view_file",
                    "target_path": "/home/kuasha/Dev/psl-agy-harness/secrets.env",
                    "command_line": "cat /home/kuasha/.ssh/id_rsa",
                }
            ],
        }

    def test_non_destructive_invariant(self):
        """Verifies original tool_call dictionary is strictly not mutated."""
        original_copy = copy.deepcopy(self.raw_tool_call)
        sanitized = sanitize_tool_call(self.raw_tool_call, workspace_root=self.workspace_root)
        self.assertEqual(self.raw_tool_call, original_copy)
        self.assertIsNot(sanitized, self.raw_tool_call)

    def test_sanitize_mode_scrubbing(self):
        """Verifies all specified fields are scrubbed in sanitize mode."""
        sanitized = sanitize_tool_call(
            self.raw_tool_call,
            workspace_root=self.workspace_root,
            mode="sanitize",
        )

        # command_line
        self.assertIn("Authorization: Bearer [REDACTED_SECRET]", sanitized["command_line"])
        self.assertIn("postgres://user:[REDACTED_PASSWORD]@localhost:5432/telemetry", sanitized["command_line"])

        # snippets
        self.assertEqual(
            sanitized["arguments_snippet"],
            "cmd: [WORKSPACE_ROOT]/run.sh --password [REDACTED_PASSWORD]",
        )
        self.assertEqual(
            sanitized["error_snippet"],
            "Error in [WORKSPACE_ROOT]/main.py: [REDACTED_API_KEY] rejected",
        )

        # target_path
        self.assertEqual(sanitized["target_path"], "[WORKSPACE_ROOT]/harness/cli.py")

        # arguments_json deserialized, scrubbed, and reserialized
        parsed_json = json.loads(sanitized["arguments_json"])
        self.assertEqual(parsed_json["CommandLine"], "export API_KEY=[REDACTED_API_KEY]")
        self.assertEqual(parsed_json["TargetFile"], "[WORKSPACE_ROOT]/tests/test_cli.py")
        self.assertEqual(parsed_json["meta"]["token"], "[REDACTED_GITHUB_TOKEN]")
        self.assertEqual(parsed_json["meta"]["step"], 42)
        self.assertTrue(parsed_json["meta"]["active"])

        # nested_calls
        nested = sanitized["nested_calls"][0]
        self.assertEqual(nested["target_path"], "[WORKSPACE_ROOT]/secrets.env")
        self.assertEqual(nested["command_line"], "cat [USER_HOME]/.ssh/id_rsa")

    def test_invalid_arguments_json_fallback(self):
        """Verifies invalid JSON in arguments_json falls back to raw text scrubbing."""
        tc = {
            "tool_name": "exec",
            "arguments_json": "Invalid JSON: token=ghp_1234567890abcdef1234567890abcdef /home/kuasha/Dev/psl-agy-harness",
        }
        sanitized = sanitize_tool_call(tc, workspace_root=self.workspace_root)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", sanitized["arguments_json"])
        self.assertIn("[WORKSPACE_ROOT]", sanitized["arguments_json"])

    def test_omit_mode(self):
        """Verifies omit mode sets sensitive fields to [OMITTED]."""
        sanitized = sanitize_tool_call(self.raw_tool_call, mode="omit")
        self.assertEqual(sanitized["command_line"], "[OMITTED]")
        self.assertEqual(sanitized["arguments_snippet"], "[OMITTED]")
        self.assertEqual(sanitized["error_snippet"], "[OMITTED]")
        self.assertEqual(sanitized["target_path"], "[OMITTED]")
        self.assertEqual(sanitized["arguments_json"], "[OMITTED]")
        self.assertEqual(sanitized["tool_name"], "run_command")

    def test_metadata_only_mode(self):
        """Verifies metadata_only mode retains only length markers."""
        sanitized = sanitize_tool_call(self.raw_tool_call, mode="metadata_only")
        self.assertTrue(sanitized["command_line"].startswith("[REDACTED len="))
        self.assertTrue(sanitized["arguments_json"].startswith("[REDACTED len="))
        self.assertTrue(sanitized["arguments_snippet"].startswith("[REDACTED len="))
        self.assertTrue(sanitized["error_snippet"].startswith("[REDACTED len="))
        self.assertTrue(sanitized["target_path"].startswith("[REDACTED len="))

    def test_invalid_mode_raises(self):
        """Verifies unsupported mode raises ValueError."""
        with self.assertRaises(ValueError):
            sanitize_tool_call(self.raw_tool_call, mode="unsupported")


class TestRedactionMicroBenchmark(unittest.TestCase):
    """Verifies sub-millisecond execution benchmark invariant (<1ms per 10KB payload)."""

    def test_latency_under_one_millisecond(self):
        """Asserts redaction latency is strictly <1.0ms per 10KB payload."""
        # Realistic 12KB source code payload
        base_line = "def process_data(records):\n    for record in records:\n        yield record.strip()\n"
        benign_10kb = base_line * 150
        self.assertGreaterEqual(len(benign_10kb), 10000)

        # Benchmark benign payload
        iterations = 25
        t0 = time.perf_counter()
        for _ in range(iterations):
            strip_secrets(benign_10kb)
        t1 = time.perf_counter()
        benign_avg_ms = ((t1 - t0) / iterations) * 1000
        self.assertLess(
            benign_avg_ms,
            1.0,
            f"Benign payload latency {benign_avg_ms:.4f}ms exceeds 1.0ms limit",
        )

        # 12KB payload with credentials injected
        secrets_10kb = (
            benign_10kb[:3000]
            + "\nAuthorization: Bearer dummy_secret_token_12345\n"
            + benign_10kb[3000:6000]
            + "\nghp_1234567890abcdef1234567890abcdef\n"
            + benign_10kb[6000:9000]
            + "\napi_key = 'abcdef1234567890'\n"
            + benign_10kb[9000:]
        )
        self.assertGreaterEqual(len(secrets_10kb), 10000)

        t0 = time.perf_counter()
        for _ in range(iterations):
            strip_secrets(secrets_10kb)
        t1 = time.perf_counter()
        secrets_avg_ms = ((t1 - t0) / iterations) * 1000
        self.assertLess(
            secrets_avg_ms,
            1.0,
            f"Secrets payload latency {secrets_avg_ms:.4f}ms exceeds 1.0ms limit",
        )


if __name__ == "__main__":
    unittest.main()
