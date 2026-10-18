import importlib.util
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rabbit_hole.py"
spec = importlib.util.spec_from_file_location("rabbit_hole", SCRIPT)
rabbit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rabbit)


class RabbitHoleTests(unittest.TestCase):
    def test_orthogonal_search_uses_official_cli(self):
        completed = rabbit.subprocess.CompletedProcess(
            args=["npx"], returncode=0,
            stdout='{"results":[{"title":"Example","url":"https://example.com","content":"Snippet"}]}',
            stderr="",
        )
        with patch.dict(os.environ, {"ORTHOGONAL_API_KEY": "test-key"}):
            with patch.object(rabbit.subprocess, "run", return_value=completed) as mocked_run:
                payload, price = rabbit.orthogonal_search("test query")
        self.assertIn("results", payload)
        self.assertIsNone(price)
        args, kwargs = mocked_run.call_args
        self.assertIn("@orth/cli", args[0])
        self.assertIn("tavily", args[0])
        self.assertIn("/search", args[0])
        self.assertIn("query=test query", args[0])
        self.assertIn("--raw", args[0])
        self.assertEqual(kwargs["env"]["ORTHOGONAL_API_KEY"], "test-key")

    def test_orthogonal_search_surfaces_cli_error(self):
        completed = rabbit.subprocess.CompletedProcess(
            args=["npx"], returncode=1, stdout="", stderr="API schema validation failed"
        )
        with patch.dict(os.environ, {"ORTHOGONAL_API_KEY": "test-key"}):
            with patch.object(rabbit.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "API schema validation failed"):
                    rabbit.orthogonal_search("test query")

    def test_normalize_tavily_style_payload(self):
        payload = {"data": {"results": [
            {"title": "Example", "url": "https://example.com/page", "content": "A snippet"},
            {"title": "Duplicate", "url": "https://example.com/page", "content": "Duplicate URL"},
            {"title": "Bad", "url": "javascript:alert(1)", "content": "Unsafe URL"},
        ]}}
        results = rabbit.normalize_results(payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example")

    def test_topic_override_wins(self):
        picked = rabbit.choose_topic(["A", "B"], [], date(2026, 10, 18), "My topic")
        self.assertEqual(picked, "My topic")

    def test_recent_topic_is_avoided(self):
        day = date(2026, 10, 18)
        picked = rabbit.choose_topic(["A", "B"], [{"date": day.isoformat(), "topic": "A"}], day)
        self.assertEqual(picked, "B")

    def test_slugify(self):
        self.assertEqual(rabbit.slugify("Why CAPTCHA? A weird story!"), "why-captcha-a-weird-story")

    def test_telegram_message_contains_topic_and_clickable_urls(self):
        topic = "The strange history of the dancing baby meme"
        results = [{
            "title": "Example source",
            "url": "https://example.com/history",
            "snippet": "A short excerpt.",
            "domain": "example.com",
        }]
        message = rabbit.build_telegram_message(topic, "topic history", results, date(2026, 10, 18))
        self.assertIn(topic, message)
        self.assertIn("https://example.com/history", message)
        self.assertIn("2026-10-18", message)
        self.assertLessEqual(len(message), 4096)


if __name__ == "__main__":
    unittest.main()
