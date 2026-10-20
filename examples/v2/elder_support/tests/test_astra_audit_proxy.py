import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PATH = Path(__file__).resolve().parents[1] / "tools/run_astra_single.py"
spec = importlib.util.spec_from_file_location("runner", PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.server = runner.AuditServer(("127.0.0.1", 0), runner.AuditHandler)
        self.server.key = "test-only-not-a-key"
        self.server.record = self.rows.append
        self.server.next_id = lambda: 1
        self.server.expected_model = runner.MODEL
        self.server.expected_effort = "medium"
        self.server.expected_provider = "openai"
        self.server.upstream = "https://example.test/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, payload, path="/v1/chat/completions"):
        return urlopen(
            Request(
                f"http://127.0.0.1:{self.server.server_port}{path}",
                data=json.dumps(payload).encode(),
            ),
            timeout=5,
        )

    def test_missing_medium_rejected_without_upstream(self):
        with patch.object(runner, "urlopen") as upstream:
            with self.assertRaises(HTTPError) as error:
                self.request({"model": runner.MODEL})
            self.assertEqual(error.exception.code, 422)
            upstream.assert_not_called()

    def test_usage_captured_without_secret_or_prompt(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(
                    {
                        "model": runner.MODEL,
                        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                        "choices": [],
                    }
                ).encode()

        with patch.object(runner, "urlopen", return_value=Response()) as upstream:
            with self.request(
                {
                    "model": runner.MODEL,
                    "reasoning_effort": "medium",
                    "messages": [{"role": "user", "content": "private prompt"}],
                }
            ) as response:
                self.assertEqual(response.status, 200)
            for thread in list(threading.enumerate()):
                if thread.name.endswith("(process_request_thread)"):
                    thread.join(timeout=2)
            self.assertEqual(self.rows[0]["usage"]["prompt_tokens"], 10)
            self.assertNotIn("private prompt", json.dumps(self.rows))
            self.assertNotIn(self.server.key, json.dumps(self.rows))
            self.assertEqual(
                json.loads(upstream.call_args.args[0].data)["reasoning_effort"], "medium"
            )

    def test_anthropic_messages_accepted(self):
        self.server.expected_model = "claude-opus-5-5"
        self.server.expected_provider = "anthropic"

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(
                    {
                        "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 4, "output_tokens": 2},
                        "content": [],
                    }
                ).encode()

        with patch.object(runner, "urlopen", return_value=Response()) as upstream:
            with self.request(
                {
                    "model": "claude-opus-5-5",
                    "thinking": {"type": "adaptive"},
                    "output_config": {"effort": "medium"},
                    "messages": [{"role": "user", "content": "secret"}],
                },
                path="/v1/v1/messages",
            ) as response:
                self.assertEqual(response.status, 200)
            for thread in list(threading.enumerate()):
                if thread.name.endswith("(process_request_thread)"):
                    thread.join(timeout=2)
            self.assertTrue(upstream.call_args.args[0].full_url.endswith("/messages"))
            self.assertNotIn("secret", json.dumps(self.rows))

    def test_anthropic_chat_completions_rejected(self):
        self.server.expected_model = "claude-opus-5-5"
        self.server.expected_provider = "anthropic"
        with patch.object(runner, "urlopen") as upstream:
            with self.assertRaises(HTTPError) as error:
                self.request(
                    {
                        "model": "claude-opus-5-5",
                        "reasoning_effort": "medium",
                    }
                )
            self.assertEqual(error.exception.code, 422)
            upstream.assert_not_called()


class ResolveRunTests(unittest.TestCase):
    def test_cli_overrides_must_match_manifest(self):
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = Path(tmp.name) / "none_s1"
        run.mkdir()
        (run / "init_config.json").write_text("{}")
        (run / "steps.yaml").write_text("steps: []\n")
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "model": "gpt-6-astra",
                    "reasoning_effort": "medium",
                    "provider": "openai",
                    "status": "prepared_not_started",
                    "config_hashes": {},
                }
            )
        )
        args = runner.parse_args(
            ["--run-dir", str(run), "--model", "claude-opus-5-5", "--provider", "anthropic"]
        )
        with self.assertRaises(SystemExit):
            runner.resolve_run(args)
        args = runner.parse_args(["--run-dir", str(run)])
        _, manifest, model, effort, provider, _ = runner.resolve_run(args)
        self.assertEqual((model, effort, provider), ("gpt-6-astra", "medium", "openai"))
        self.assertEqual(manifest["model"], "gpt-6-astra")


if __name__ == "__main__":
    unittest.main()
