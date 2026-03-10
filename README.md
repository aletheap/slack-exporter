# Slack Exporter

Exports all private Slack channels your bot token is a member of in the [official Slack export format](https://slack.com/help/articles/201658943-Export-your-workspace-data), then packages everything into a ZIP archive.

## Output format

```
slack_export_YYYYMMDD_HHMMSS/
├── users.json
├── channels.json
├── emoji.json
├── __emoji/
│   └── <name>.<ext>
└── <channel-name>/
    ├── YYYY-MM-DD.json
    └── _files/
        └── <file-id>-<filename>
```

## Setup

```bash
pip install -r requirements.txt
```

Create a [Slack app](https://api.slack.com/apps) and add a bot token with these OAuth scopes:

| Scope | Purpose |
|-------|---------|
| `groups:read` | List private channels the bot is a member of |
| `groups:history` | Read private channel message history |
| `users:read` | Fetch workspace user list |
| `emoji:read` | Fetch custom workspace emoji |
| `files:read` | Download file attachments |
| `metadata.message:read` | Include structured message metadata |

Install the app to your workspace, then invite the bot to each private channel you want to export (`/invite @your-bot`).

## Usage

```bash
export SLACK_TOKEN=xoxb-...
python slack_exporter.py
```

Or pass the token directly:

```bash
python slack_exporter.py --token xoxb-...
```

### Options

| Flag | Description |
|------|-------------|
| `--token TOKEN` | Slack bot/user OAuth token (or set `SLACK_TOKEN` env var) |
| `--output DIR` | Output directory (default: `slack_export_YYYYMMDD_HHMMSS`) |
| `--channel NAME` | Export only the named channel (e.g. `general`) |
| `--no-files` | Skip downloading file attachments and emoji |
| `--list-channels` | Print accessible channels and exit without exporting |

### Examples

```bash
# List channels the bot can access
python slack_exporter.py --list-channels

# Export everything
python slack_exporter.py

# Export one channel, skip file downloads
python slack_exporter.py --channel engineering --no-files
```
