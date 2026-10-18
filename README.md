# 🐇 Internet Rabbit Hole

A tiny daily research bot. GitHub Actions picks a curiosity topic, calls one web-search endpoint through Orthogonal, and commits a Markdown trail of source links and follow-up questions.

**MVP philosophy:** one search call per run, no model-generated claims, no always-on server. Search snippets are leads—not verified facts. Read the linked sources before repeating a claim.

## What it does

1. Runs every day at **08:00 Vietnam time** (01:00 UTC).
2. Chooses a topic from [`topics.txt`](topics.txt), trying not to reuse one from the last 30 days.
3. Calls Tavily through the official Orthogonal CLI (`npx @orth/cli run ... --raw`) so endpoint routing and parameter handling are delegated to the supported client.
4. Writes `journal/rabbit-holes/YYYY-MM-DD-topic.md` and updates [`journal/index.md`](journal/index.md).
5. Saves a small topic history in `data/history.json` to avoid repetition.
6. If Telegram secrets are configured, sends a daily digest with up to three clickable source links through your Telegram bot.

The workflow can also be started manually and given a specific topic. Telegram delivery is optional; without its two secrets, the journal still gets generated and committed.

## Set it up

### 1. Create the repo

Create a GitHub repository and upload/push these files. Keep it private if you do not want your journal to be public.

### 2. Add the Orthogonal secret

1. Create an API key in your [Orthogonal account](https://orthogonal.com/).
2. In the repo, open **Settings → Secrets and variables → Actions → New repository secret**.
3. Name it `ORTHOGONAL_API_KEY` and paste the key as the value. Never commit the key to Git.

### 3. Optional: send the daily results to Telegram

1. In Telegram, open **@BotFather**, send `/newbot`, and follow the prompts. Save the token it returns.
2. Open your new bot using its `t.me` link, press **Start**, and send `/start` in the private chat. Telegram requires the user to start a private chat before the bot can message them.
3. Retrieve your chat ID. On Windows PowerShell, run the following, then paste the token when prompted:

   ```powershell
   $secure = Read-Host "Paste Telegram bot token" -AsSecureString
   $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
   try {
     $env:TELEGRAM_BOT_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
     $updates = Invoke-RestMethod -Uri "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/getUpdates"
     $updates.result | ForEach-Object { if ($_.message) { [PSCustomObject]@{ chat_id = $_.message.chat.id; type = $_.message.chat.type; username = $_.message.chat.username; title = $_.message.chat.title } } } | Format-Table -AutoSize
   } finally {
     if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
     Remove-Item Env:\TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
   }
   ```

   Use the `chat_id` on the `private` row. If no row appears, send `/start` to the bot and retry. For a group, add the bot to the group and use that group's `message.chat.id`. For a channel, make the bot an administrator with permission to post; public channels can use `@channelusername`.
4. In your GitHub repo, open **Settings → Secrets and variables → Actions → New repository secret** and create:
   - `TELEGRAM_BOT_TOKEN` — token from @BotFather
   - `TELEGRAM_CHAT_ID` — private chat/group ID or `@channelusername`
5. Run the workflow manually once. After each successful search, the bot sends the topic, query, up to three links, and follow-up trails. It uses Telegram's Bot API directly, so it does not consume Orthogonal search credits.

Never commit the Telegram token to code or YAML. If Telegram delivery fails temporarily, the workflow logs a warning but still commits the generated journal.

### 4. Check the provider endpoint and its price

This starter defaults to `tavily` + `/search`, using the same route shown in the Orthogonal CLI's quick-start examples. Provider schemas and pricing can change, so inspect the live definition before the first billable run:

```bash
npx @orth/cli api show tavily /search
npx @orth/cli run tavily /search --dry-run -q 'query=why old websites survive'
```

If your account/catalog exposes a different search provider or parameter schema, update `ORTHOGONAL_SEARCH_API` and `ORTHOGONAL_SEARCH_PATH` in the workflow. The current code intentionally sends only the documented `query` parameter to avoid passing unverified provider-specific fields. You can search the catalog with:

```bash
npx @orth/cli api search "low-cost web search returning titles, URLs, and snippets"
```

### 5. Enable Actions write permission

The workflow declares `permissions: contents: write` so it can commit generated Markdown and history. In repository **Settings → Actions → General**, check that workflow permissions are not restricted by an organization policy.

### 6. Run a manual test

Open **Actions → Internet Rabbit Hole → Run workflow**. You may enter a topic such as:

```text
The strange history of the dancing baby meme
```

Leave the topic blank to choose automatically. Open the workflow run and inspect its log. On success, it commits one article and updates `journal/index.md`.

## Run locally

Python 3.10+ is recommended (3.12 is used in Actions). No `pip install` is required.

```bash
# macOS/Linux
export ORTHOGONAL_API_KEY="your_key_here"
RABBIT_HOLE_TOPIC="The hidden story behind the default blue hyperlink" python scripts/rabbit_hole.py

# Windows PowerShell
$env:ORTHOGONAL_API_KEY="your_key_here"
$env:RABBIT_HOLE_TOPIC="The hidden story behind the default blue hyperlink"
python scripts/rabbit_hole.py
```

Do not paste a real key into a committed script, notebook, workflow YAML, or issue.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `ORTHOGONAL_API_KEY` | — | Required secret |
| `ORTHOGONAL_SEARCH_API` | `tavily` | Orthogonal provider slug |
| `ORTHOGONAL_SEARCH_PATH` | `/search` | Provider endpoint path |
| `MAX_RESULTS` | `5` | Maximum number of returned results retained in the journal (3–8) |
| `SEARCH_SUFFIX` | `strange history surprising facts explained` | Added to each topic query |
| `RABBIT_HOLE_TOPIC` | empty | Override the selected topic for a run |
| `TELEGRAM_BOT_TOKEN` | empty | Optional Telegram bot token; configured as a GitHub secret |
| `TELEGRAM_CHAT_ID` | empty | Optional private chat/group ID or `@channelusername` |

## Cost and safety guardrails

- The workflow makes **one Orthogonal search request per execution** through the official Orthogonal CLI. The default $10 Orthogonal starter credit is not a guarantee of unlimited usage; the selected endpoint's current price applies.
- The code does not call an LLM and does not scrape each result. It publishes links and returned excerpts to keep the initial experiment inexpensive. Telegram delivery uses the Bot API and does not spend Orthogonal credits.
- Check the endpoint schema and use the CLI's `--dry-run` before the first live request. Keep `MAX_RESULTS` small.
- Never let page text or search snippets trigger shell commands or workflow edits. This project treats fetched data as untrusted content and only writes Markdown.
- Review source URLs, dates, and context. Search snippets may be wrong or incomplete.

## Next upgrades

1. Add an optional second Orthogonal call to an LLM endpoint for a 150-word source-grounded story (after checking the exact current model endpoint schema and cost).
2. Scrape only one or two promising pages when snippet quality is poor.
3. Add RSS or a GitHub Pages front end.
4. Add a `source_quality` score and detect duplicate URLs across days.

## Reference links

- [Orthogonal quickstart](https://docs.orthogonal.com/quickstart)
- [Orthogonal pricing](https://www.orthogonal.com/pricing)
- [Orthogonal CLI](https://github.com/orthogonal-sh/cli)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [Telegram bot tutorial](https://core.telegram.org/bots/tutorial)
- [Telegram Bot API: sendMessage](https://core.telegram.org/bots/api#sendmessage)
