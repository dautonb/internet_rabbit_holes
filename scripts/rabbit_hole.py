#!/usr/bin/env python3
"""Daily Internet Rabbit Hole: one Orthogonal-backed web search -> Markdown journal.

Uses only the Python standard library. The default Orthogonal provider is Tavily
(search endpoint /search), but both provider slug and path are configurable.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TOPICS_FILE = ROOT / "topics.txt"
HISTORY_FILE = ROOT / "data" / "history.json"
ARTICLES_DIR = ROOT / "journal" / "rabbit-holes"
INDEX_FILE = ROOT / "journal" / "index.md"
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def local_today() -> date:
    return datetime.now(TIMEZONE).date()


def read_topics() -> list[str]:
    if not TOPICS_FILE.exists():
        raise RuntimeError(f"Missing topic list: {TOPICS_FILE}")
    topics = [line.strip() for line in TOPICS_FILE.read_text(encoding="utf-8").splitlines()]
    topics = [line for line in topics if line and not line.startswith("#")]
    if not topics:
        raise RuntimeError("topics.txt has no usable topics")
    return topics


def load_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, OSError):
        print("Warning: history.json is unreadable; starting with an empty history.", file=sys.stderr)
        return []


def choose_topic(topics: list[str], history: list[dict[str, Any]], today: date, override: str = "") -> str:
    """Choose a topic not used in the last 30 days; date-seeded for reproducibility."""
    override = override.strip()
    if override:
        return override

    used_recently: set[str] = set()
    for entry in history:
        try:
            used_date = date.fromisoformat(str(entry.get("date", "")))
            if 0 <= (today - used_date).days < 30:
                used_recently.add(str(entry.get("topic", "")))
        except (TypeError, ValueError):
            continue

    eligible = [topic for topic in topics if topic not in used_recently]
    if not eligible:
        # If the configured list is smaller than the repeat window, fall back to all topics.
        eligible = topics

    # Stable ordering for the same date, without requiring third-party dependencies.
    eligible = sorted(eligible, key=lambda t: __import__("hashlib").sha256(f"{today.isoformat()}::{t}".encode()).hexdigest())
    return eligible[0]


def configured_max_results() -> int:
    try:
        return max(3, min(int(os.environ.get("MAX_RESULTS", "5")), 8))
    except ValueError:
        return 5


def orthogonal_search(query: str) -> tuple[dict[str, Any], str | None]:
    """Search through Orthogonal's official CLI to avoid hand-building gateway requests.

    Orthogonal documents `orth run tavily /search -q query=... --raw` as the
    supported invocation. The CLI resolves the endpoint metadata and emits raw
    JSON, while ORTHOGONAL_API_KEY is read from the environment in CI.
    """
    api_key = os.environ.get("ORTHOGONAL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ORTHOGONAL_API_KEY is missing. Add it to GitHub Actions Secrets or your shell environment.")

    api_slug = os.environ.get("ORTHOGONAL_SEARCH_API", "tavily").strip()
    api_path = os.environ.get("ORTHOGONAL_SEARCH_PATH", "/search").strip()
    if not api_path.startswith("/"):
        api_path = "/" + api_path

    # Keep to the documented query argument first. Extra parameters can be
    # added once confirmed against `orth api show <provider> <path>`; guessing
    # endpoint-specific fields can trigger upstream HTTP 422 errors.
    command = [
        "npx", "--yes", "@orth/cli", "run", api_slug, api_path,
        "-q", f"query={query}", "--raw",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        raise RuntimeError("Node.js/npm is missing; GitHub Actions must set up Node.js before running the search.") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("Orthogonal CLI search timed out after 90 seconds.") from None

    if completed.returncode != 0:
        # CLI errors are useful to diagnose schema/auth/credit failures. Never
        # echo the environment or request headers, which may contain secrets.
        detail = (completed.stderr or completed.stdout or "No error details returned by Orthogonal CLI.").strip()
        detail = detail.replace(api_key, "[REDACTED]")
        detail = re.sub(r"\s+", " ", detail)[:700]
        raise RuntimeError(f"Orthogonal CLI search failed (exit {completed.returncode}): {detail}")

    raw_output = completed.stdout.strip()
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        # Be tolerant if an npm/CLI notice precedes the JSON payload, while
        # still requiring an actual JSON object/array in the output.
        first_obj = raw_output.find("{")
        first_arr = raw_output.find("[")
        candidates = [pos for pos in (first_obj, first_arr) if pos >= 0]
        if not candidates:
            raise RuntimeError("Orthogonal CLI returned no JSON. Re-run `npx @orth/cli run tavily /search -q query=... --raw` locally to inspect output.") from None
        start = min(candidates)
        try:
            payload = json.loads(raw_output[start:])
        except json.JSONDecodeError:
            raise RuntimeError("Orthogonal CLI output was not valid JSON. Check the CLI version and endpoint response.") from None

    if not isinstance(payload, dict):
        raise RuntimeError(f"Orthogonal CLI returned unexpected JSON type: {type(payload).__name__}")
    if payload.get("success") is False or payload.get("ok") is False:
        detail = payload.get("error") or payload.get("message") or "request failed"
        raise RuntimeError(f"Orthogonal search failed: {str(detail)[:500]}")

    price = payload.get("price")
    if price is None and isinstance(payload.get("billing"), dict):
        price = payload["billing"].get("price")
    if price is None and isinstance(payload.get("_meta"), dict):
        price = payload["_meta"].get("price")
    return payload, str(price) if price is not None else None


def _find_result_list(value: Any, depth: int = 0) -> list[dict[str, Any]]:
    """Find common search-result list shapes without assuming one provider response schema."""
    if depth > 5:
        return []
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            if any(any(key in item for key in ("url", "link", "href", "title", "name")) for item in value):
                return value
        for item in value:
            found = _find_result_list(item, depth + 1)
            if found:
                return found
        return []
    if isinstance(value, dict):
        for key in ("results", "organic_results", "web_results", "documents", "items", "data"):
            if key in value:
                found = _find_result_list(value[key], depth + 1)
                if found:
                    return found
        for item in value.values():
            if isinstance(item, (dict, list)):
                found = _find_result_list(item, depth + 1)
                if found:
                    return found
    return []


def normalize_results(payload: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
    raw_results = _find_result_list(payload)
    normalized: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
        title = str(item.get("title") or item.get("name") or "Untitled result").strip()
        snippet = str(item.get("content") or item.get("snippet") or item.get("description") or item.get("excerpt") or item.get("text") or "").strip()
        if not url.startswith(("https://", "http://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        snippet = re.sub(r"\s+", " ", snippet)
        if len(snippet) > 700:
            snippet = snippet[:697].rstrip() + "…"
        host = urllib.parse.urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        normalized.append({"title": title, "url": url, "snippet": snippet, "domain": host})
        if len(normalized) >= limit:
            break
    return normalized


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")[:65] or "rabbit-hole"


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def make_search_query(topic: str) -> str:
    suffix = os.environ.get("SEARCH_SUFFIX", "strange history surprising facts explained")
    return f"{topic} {suffix}".strip()


def render_article(topic: str, query: str, results: list[dict[str, str]], day: date, price: str | None) -> str:
    lines = [
        "---",
        f'title: "{topic.replace(chr(34), chr(39))}"',
        f"date: {day.isoformat()}",
        "layout: default",
        "---",
        "",
        f"# 🐇 {topic}",
        "",
        f"> A daily Internet Rabbit Hole · {day.strftime('%d %b %Y')}",
        "",
        "## The question",
        "",
        f"**Search trail:** `{query}`",
        "",
        "This page is a source-first research trail. Start with the links below, compare what each source actually says, and follow the next questions wherever they lead. The snippets are search-provider excerpts, not independently verified conclusions.",
        "",
        "## Follow the trail",
        "",
    ]

    if not results:
        lines.extend([
            "No usable search results were returned. Check the provider schema and try the workflow again.",
            "",
        ])
    else:
        for index, result in enumerate(results, 1):
            lines.extend([
                f"### {index}. [{md_escape(result['title'])}]({result['url']})",
                "",
                f"<sub>{md_escape(result['domain'])}</sub>",
                "",
                result["snippet"] or "No excerpt was returned. Open the source to inspect it directly.",
                "",
            ])

    lines.extend([
        "## Three paths deeper",
        "",
        f"1. **Origin story:** `{topic} origin and early history`",
        f"2. **The weird edge cases:** `{topic} unusual examples and unexpected uses`",
        f"3. **The skeptical view:** `{topic} myths, criticism, and misconceptions`",
        "",
        "## Rabbit-hole rules",
        "",
        "- Prefer primary sources, documentation, papers, archives, or first-hand accounts when available.",
        "- Treat a search snippet as a lead, not proof. Open the source and check dates and context.",
        "- If two sources disagree, keep both links and write down what would resolve the disagreement.",
        "",
        "---",
        "",
        "*Generated automatically by [Internet Rabbit Hole](../../README.md) using Orthogonal. Review the sources before treating any claim as fact.*",
    ])
    if price:
        lines.extend(["", f"<sub>Reported Orthogonal request price: `${md_escape(price)}` (if supplied by the API response).</sub>"])
    lines.append("")
    return "\n".join(lines)


def update_index(article_path: Path, topic: str, day: date, results_count: int, price: str | None) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for path in sorted(ARTICLES_DIR.glob("*.md"), reverse=True):
        if path == article_path:
            continue
        try:
            first_lines = path.read_text(encoding="utf-8").splitlines()[:12]
        except OSError:
            continue
        title = path.stem
        for line in first_lines:
            if line.startswith("# 🐇 "):
                title = line.removeprefix("# 🐇 ").strip()
                break
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        entry_date = date_match.group(1) if date_match else ""
        entries.append({"date": entry_date, "title": title, "file": path.name})

    # Include the current article, then sort newest first.
    entries.insert(0, {"date": day.isoformat(), "title": topic, "file": article_path.name})
    entries.sort(key=lambda item: (item["date"], item["file"]), reverse=True)

    lines = [
        "# 🐇 Internet Rabbit Hole Journal",
        "",
        "One small detour down the Internet every day. Each entry is a trail of links and follow-up questions, not an authoritative fact-check.",
        "",
        f"**Latest run:** {day.isoformat()} · **Search results:** {results_count}" + (f" · **Reported price:** ${price}" if price else ""),
        "",
        "## Archive",
        "",
    ]
    for entry in entries[:200]:
        lines.append(f"- **{entry['date']}** — [{entry['title']}](rabbit-holes/{entry['file']})")
    lines.extend(["", "## Run it yourself", "", "See the [project README](../README.md) for setup instructions.", ""])
    INDEX_FILE.write_text("\n".join(lines), encoding="utf-8")


def save_history(history: list[dict[str, Any]], topic: str, query: str, day: date, price: str | None) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history.append({"date": day.isoformat(), "topic": topic, "query": query, "price": price})
    # Keep a small file that is easy to commit to Git.
    HISTORY_FILE.write_text(json.dumps(history[-120:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def build_telegram_message(topic: str, query: str, results: list[dict[str, str]], day: date) -> str:
    """Build a short, plain-text Telegram digest with clickable source URLs."""
    lines = [
        "🐇 INTERNET RABBIT HOLE",
        f"📅 {day.isoformat()}",
        "",
        f"🕳 {topic[:240]}",
        "",
        f"🔎 Search trail: {query[:300]}",
        "",
        "🌐 Nguồn để khám phá:",
    ]

    for index, result in enumerate(results[:3], 1):
        url = result.get("url", "").strip()
        if not url.startswith(("https://", "http://")) or len(url) > 1200:
            continue
        title = re.sub(r"\s+", " ", result.get("title", "Untitled source")).strip()[:160]
        snippet = re.sub(r"\s+", " ", result.get("snippet", "")).strip()[:190]
        block = [f"\n{index}. {title}", url]
        if snippet:
            block.append(snippet)
        # Keep a generous margin below Telegram's 4096-character sendMessage limit.
        candidate = "\n".join(lines + block)
        if len(candidate) > 3600 and snippet:
            block[-1] = snippet[:80] + "…"
            candidate = "\n".join(lines + block)
        if len(candidate) <= 3600:
            lines.extend(block)

    lines.extend([
        "",
        "🧭 Đi sâu hơn:",
        f"• Nguồn gốc: {topic[:140]} origin and early history",
        f"• Góc kỳ quặc: {topic[:140]} unusual examples",
        f"• Góc hoài nghi: {topic[:140]} myths and misconceptions",
        "",
        "_Bot tự động tìm nguồn; snippet chưa phải kết luận đã kiểm chứng._",
    ])
    message = "\n".join(lines).strip()
    if len(message) > 3900:
        message = message[:3880].rsplit("\n", 1)[0] + "\n…"
    return message


def send_telegram_message(message: str) -> bool:
    """Send a plain-text message through the Telegram Bot API.

    Telegram settings are optional, so the journal still works without them.
    Never include the bot token in logs or error messages.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token and not chat_id:
        print("Telegram secrets are not configured; skipping Telegram delivery.")
        return False
    if not token or not chat_id:
        raise RuntimeError("Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Actions Secrets.")
    if len(message) > 4096:
        message = message[:4080].rsplit("\n", 1)[0] + "\n…"

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            if isinstance(error_payload, dict):
                detail = str(error_payload.get("description", ""))[:240]
        except Exception:
            pass
        # Deliberately do not include str(exc), since it may contain the token URL.
        raise RuntimeError(f"Telegram HTTP {exc.code}. {detail}".strip()) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Could not reach the Telegram API (network error or timeout).") from None
    except json.JSONDecodeError:
        raise RuntimeError("Telegram returned a non-JSON response.") from None

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        detail = payload.get("description", "unknown Telegram API error") if isinstance(payload, dict) else "unexpected API response"
        raise RuntimeError(f"Telegram API rejected the message: {str(detail)[:240]}")
    return True

def main() -> int:
    today = local_today()
    history = load_history()
    topic = choose_topic(read_topics(), history, today, os.environ.get("RABBIT_HOLE_TOPIC", ""))
    query = make_search_query(topic)
    print(f"Rabbit hole for {today.isoformat()}: {topic}")
    print(f"Search provider: {os.environ.get('ORTHOGONAL_SEARCH_API', 'tavily')} {os.environ.get('ORTHOGONAL_SEARCH_PATH', '/search')}")

    payload, price = orthogonal_search(query)
    results = normalize_results(payload, limit=configured_max_results())
    if not results:
        # Fail loudly instead of committing an empty/possibly malformed page.
        top_keys = ", ".join(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        raise RuntimeError(f"Search call succeeded but no recognizable results were found (top-level shape: {top_keys}). Inspect the provider response and adjust normalize_results().")

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    article_path = ARTICLES_DIR / f"{today.isoformat()}-{slugify(topic)}.md"
    article_path.write_text(render_article(topic, query, results, today, price), encoding="utf-8")
    update_index(article_path, topic, today, len(results), price)
    save_history(history, topic, query, today, price)

    telegram_message = build_telegram_message(topic, query, results, today)
    try:
        if send_telegram_message(telegram_message):
            print("Telegram notification sent successfully.")
    except RuntimeError as exc:
        # Do not fail the whole job: let GitHub Actions commit the generated journal
        # even if Telegram has a temporary issue. The warning remains visible in logs.
        print(f"::warning::Telegram notification failed: {exc}. Journal will still be committed.", file=sys.stderr)

    print(f"Wrote: {article_path.relative_to(ROOT)}")
    print(f"Results: {len(results)}")
    if price:
        print(f"Orthogonal reported price: ${price}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
