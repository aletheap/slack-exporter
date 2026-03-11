#!/usr/bin/env python3
"""
Slack Workspace Exporter

Exports all public channels and all private channels the token is a member
of from a Slack workspace in the official Slack export format (channels.json,
users.json, and per-channel daily message files), then packages everything
into a ZIP archive.

Required OAuth token scopes:
  channels:read    — list public channels
  channels:history — read public channel message history
  channels:join    — join public channels to read their history
  groups:read      — list private channels the token is a member of
  groups:history   — read private channel message history
  users:read       — fetch workspace user list
  emoji:read       — fetch custom workspace emoji
  files:read       — download file attachments
  metadata.message:read — include structured message metadata in history

Usage:
  export SLACK_TOKEN=xoxb-...
  python slack_exporter.py

  # or pass token directly:
  python slack_exporter.py --token xoxb-...
"""

import argparse
import json
import os
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print("Error: slack-sdk not installed. Run: pip install slack-sdk")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm not installed. Run: pip install tqdm")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class SlackExporter:
    """Exports a Slack workspace to the official export format."""

    def __init__(self, token: str, output_dir: str = None, download_files: bool = True):
        self.client = WebClient(token=token)
        self.out = Path(output_dir) if output_dir else None
        self.download_files = download_files
        # Reuse one session for all file downloads; auth header sent automatically.
        self._http = requests.Session()
        self._http.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call(self, method: str, **kwargs):
        """Wrapper around the Slack SDK that handles rate-limit retries."""
        while True:
            try:
                fn = getattr(self.client, method)
                return fn(**kwargs)
            except SlackApiError as exc:
                if exc.response["error"] == "ratelimited":
                    wait = int(exc.response.headers.get("Retry-After", 60))
                    ts = datetime.now().strftime("%I:%M:%S %p")
                    tqdm.write(f"    [{ts}] [rate limit] waiting {wait}s …")
                    time.sleep(wait)
                else:
                    raise

    def _paginate(self, method: str, result_key: str, **kwargs):
        """Yield all items from a paginated Slack API endpoint."""
        cursor = None
        while True:
            if cursor:
                kwargs["cursor"] = cursor
            result = self._call(method, **kwargs)
            yield from result.get(result_key, [])
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    # ------------------------------------------------------------------
    # Data fetchers
    # ------------------------------------------------------------------

    def fetch_users(self):
        users = []
        with tqdm(desc="Fetching users", unit=" user", leave=True) as pbar:
            for user in self._paginate("users_list", "members", limit=200):
                users.append(user)
                pbar.update(1)
        return users

    def fetch_channels(self, allowlist: set = None, denylist: set = None):
        channels = []
        with tqdm(desc="Fetching channels", unit=" ch", leave=True) as pbar:
            for ch in self._paginate(
                "conversations_list",
                "channels",
                types="private_channel,public_channel",
                exclude_archived=False,
                limit=200,
            ):
                if allowlist is not None and ch["name"] not in allowlist:
                    continue
                if denylist and ch["name"] in denylist:
                    continue
                channels.append(ch)
                pbar.update(1)
        return channels

    def fetch_members(self, channel_id: str, channel_name: str = ""):
        prefix = f"#{channel_name}: " if channel_name else ""
        try:
            return list(self._paginate(
                "conversations_members", "members",
                channel=channel_id, limit=200,
            ))
        except SlackApiError as exc:
            tqdm.write(f"    [warn] {prefix}could not fetch members: {exc.response['error']}")
            return []

    def fetch_history(self, channel_id: str, channel_name: str = ""):
        """Return all messages in a channel (oldest first)."""
        prefix = f"#{channel_name}: " if channel_name else ""
        messages = []
        try:
            with tqdm(desc="  messages", unit=" msg", leave=False) as pbar:
                for msg in self._paginate(
                    "conversations_history", "messages",
                    channel=channel_id, limit=200, include_all_metadata=True,
                ):
                    messages.append(msg)
                    pbar.update(1)
        except SlackApiError as exc:
            tqdm.write(f"    [warn] {prefix}could not read history: {exc.response['error']}")
        # conversations_history returns newest-first; reverse to oldest-first
        messages.reverse()
        return messages

    def fetch_replies(self, channel_id: str, thread_ts: str, channel_name: str = ""):
        """
        Return reply messages for a thread (excludes the parent message
        so it is not duplicated in the output).
        """
        prefix = f"#{channel_name}: " if channel_name else ""
        try:
            gen = self._paginate(
                "conversations_replies", "messages",
                channel=channel_id, ts=thread_ts, limit=200,
            )
            next(gen, None)  # skip parent message (always first item on page 1)
            return list(gen)
        except SlackApiError as exc:
            tqdm.write(f"    [warn] {prefix}thread {thread_ts}: {exc.response['error']}")
            return []

    # ------------------------------------------------------------------
    # File download helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_files(messages: list) -> list:
        """Return a deduplicated list of file objects found in messages."""
        seen, files = set(), []
        for msg in messages:
            for f in msg.get("files", []):
                fid = f.get("id")
                # Skip deleted files (Slack marks them as "tombstone")
                if fid and fid not in seen and f.get("mode") != "tombstone":
                    seen.add(fid)
                    files.append(f)
        return files

    def _download_file(self, url: str, dest: Path) -> bool:
        """Stream a private Slack file to *dest*. Returns True on success."""
        if dest.exists():
            return True  # already downloaded (resumable re-runs)
        try:
            resp = self._http.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)
            return True
        except Exception as exc:
            tqdm.write(f"    [warn] download failed {dest.name}: {exc}")
            dest.unlink(missing_ok=True)  # remove any partial write
            return False

    def download_channel_files(self, messages: list, ch_dir: Path):
        """Download all file attachments referenced in *messages* to *ch_dir*/_files/."""
        files = self._collect_files(messages)
        if not files:
            return
        files_dir = ch_dir / "_files"
        files_dir.mkdir(exist_ok=True)
        bar = tqdm(files, desc="  files", unit=" file", leave=False)
        for f in bar:
            url = f.get("url_private_download") or f.get("url_private")
            if not url:
                continue
            name = f.get("name") or f.get("id", "unknown")
            dest = files_dir / f"{f['id']}-{name}"
            bar.set_postfix_str(name[:40])
            self._download_file(url, dest)
            # Relative to the channel dir so the path works regardless of
            # where the export folder lives.
            f["local_path"] = f"_files/{dest.name}"

    # ------------------------------------------------------------------
    # Emoji helpers
    # ------------------------------------------------------------------

    def fetch_emoji(self) -> dict:
        """Return the workspace custom emoji map {name: url_or_alias}."""
        result = self._call("emoji_list")
        return result.get("emoji", {})

    def download_emoji(self, emoji: dict):
        """Download all non-alias custom emoji images to __emoji/ in the output dir."""
        # Aliases point to other emoji names ("alias:other-name"), not URLs.
        to_download = {name: url for name, url in emoji.items()
                       if not url.startswith("alias:")}
        if not to_download:
            return
        emoji_dir = self.out / "__emoji"
        emoji_dir.mkdir(exist_ok=True)
        bar = tqdm(to_download.items(), desc="Emoji", unit=" emoji", leave=True)
        for name, url in bar:
            ext = Path(url.split("?")[0]).suffix or ".png"
            dest = emoji_dir / f"{name}{ext}"
            bar.set_postfix_str(name[:40])
            self._download_file(url, dest)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_channel(channel: dict, members: list) -> dict:
        """Trim a channel object to the fields present in official exports."""
        blank_set = {"value": "", "creator": "", "last_set": 0}
        return {
            "id": channel.get("id"),
            "name": channel.get("name"),
            "created": channel.get("created"),
            "creator": channel.get("creator"),
            "is_archived": channel.get("is_archived", False),
            "is_general": channel.get("is_general", False),
            "members": members,
            "topic": channel.get("topic", blank_set),
            "purpose": channel.get("purpose", blank_set),
        }

    @staticmethod
    def _ts_to_day(ts: str) -> str:
        """Convert a Slack timestamp ('1234567890.123456') to 'YYYY-MM-DD'."""
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _group_by_day(messages: list) -> dict:
        """Group messages into {YYYY-MM-DD: [msg, …]} sorted by timestamp."""
        by_day: dict = defaultdict(list)
        for msg in messages:
            day = SlackExporter._ts_to_day(msg.get("ts", "0"))
            by_day[day].append(msg)
        for day in by_day:
            by_day[day].sort(key=lambda m: float(m.get("ts", 0)))
        return dict(sorted(by_day.items()))

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_json(path: Path, data):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Main export
    # ------------------------------------------------------------------

    def export(self, allowlist: set = None, denylist: set = None) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)

        # 1. Users
        users = self.fetch_users()
        self._write_json(self.out / "users.json", users)

        # 2. Custom emoji
        emoji = self.fetch_emoji()
        self._write_json(self.out / "emoji.json", emoji)
        if self.download_files:
            self.download_emoji(emoji)

        # 3. Channels + messages
        channels = self.fetch_channels(allowlist=allowlist, denylist=denylist)
        if allowlist:
            missing = allowlist - {ch["name"] for ch in channels}
            if missing:
                tqdm.write(f"    [warn] channels not found or not accessible: {', '.join(sorted(missing))}")
            if not channels:
                print("Error: none of the specified channels were found or accessible.")
                sys.exit(1)
        channels_meta = []

        ch_bar = tqdm(sorted(channels, key=lambda c: c["name"]), desc="Channels", unit=" ch")
        for ch in ch_bar:
            cid = ch["id"]
            name = ch["name"]
            is_public = not ch.get("is_private", False)
            was_member = ch.get("is_member", True)
            ch_bar.set_postfix_str(f"#{name}")

            is_archived = ch.get("is_archived", False)

            # Join public channels the bot isn't already in.
            # Archived channels cannot be joined, and conversations.unarchive
            # also requires membership — so archived public channels the bot
            # was never in cannot be exported via the Slack API with a bot
            # token. Skip them with an explanation.
            if is_public and not was_member:
                if is_archived:
                    tqdm.write(
                        f"    [skip] #{name}: archived public channel the bot was never in "
                        f"(Slack API does not allow joining or unarchiving without prior membership)"
                    )
                    continue
                try:
                    self._call("conversations_join", channel=cid)
                except SlackApiError as exc:
                    tqdm.write(
                        f"    [warn] #{name}: could not join ({exc.response['error']}), skipping"
                    )
                    continue

            members = self.fetch_members(cid, name)
            channels_meta.append(self._format_channel(ch, members))

            # --- messages + thread replies ---
            messages = self.fetch_history(cid, name)

            seen_ts: set = {m["ts"] for m in messages}
            thread_parents = [
                m for m in messages
                if m.get("reply_count", 0) > 0
                and m.get("thread_ts") == m.get("ts")
            ]
            if thread_parents:
                for parent in tqdm(
                    thread_parents,
                    desc="  threads",
                    unit=" thread",
                    leave=False,
                ):
                    for reply in self.fetch_replies(cid, parent["thread_ts"], name):
                        if reply["ts"] not in seen_ts:
                            messages.append(reply)
                            seen_ts.add(reply["ts"])

            # Sort all messages (oldest first) before grouping
            messages.sort(key=lambda m: float(m.get("ts", 0)))

            # --- download attachments (patches local_path into message dicts) ---
            ch_dir = self.out / name
            ch_dir.mkdir(exist_ok=True)
            if self.download_files:
                self.download_channel_files(messages, ch_dir)

            # --- write daily files (local_path fields already set above) ---
            by_day = self._group_by_day(messages)
            for day, day_msgs in by_day.items():
                self._write_json(ch_dir / f"{day}.json", day_msgs)

        self._write_json(self.out / "channels.json", channels_meta)

        # 4. ZIP archive
        zip_path = self.out.with_suffix(".zip")
        all_files = [fp for fp in sorted(self.out.rglob("*")) if fp.is_file()]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in tqdm(all_files, desc="Zipping", unit=" file"):
                zf.write(fp, fp.relative_to(self.out.parent))

        print(f"\nDone.")
        print(f"  Directory : {self.out}")
        print(f"  Archive   : {zip_path}")
        return zip_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export all public Slack channels in the official export format."
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("SLACK_TOKEN"),
        help="Slack Bot/User OAuth token (env: SLACK_TOKEN)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Full path for the output directory (default: slack_export_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        metavar="DIR",
        help="Parent directory for backups; each run creates a timestamped subdirectory inside it",
    )
    parser.add_argument(
        "--no-files",
        action="store_true",
        help="Skip downloading file attachments (images, videos, PDFs, etc.)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate a browsable HTML viewer after the export completes",
    )
    parser.add_argument(
        "--no-avatars",
        action="store_true",
        help="When used with --html, skip downloading user profile images",
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        help="Print accessible channels and exit without exporting",
    )
    parser.add_argument(
        "--channel",
        nargs="+",
        default=None,
        metavar="NAME",
        help="Export only these channels (space-separated, e.g. --channel general engineering)",
    )
    parser.add_argument(
        "--skip-channel",
        nargs="+",
        default=None,
        metavar="NAME",
        help="Skip these channels (space-separated, e.g. --skip-channel random announcements)",
    )
    args = parser.parse_args()

    if not args.token:
        parser.error(
            "No token supplied. Use --token or set the SLACK_TOKEN environment variable.\n\n"
            "Required OAuth scopes:\n"
            "  channels:read    – list public channels\n"
            "  channels:history – read public channel message history\n"
            "  channels:join    – join public channels to read their history\n"
            "  groups:read      – list private channels the token is a member of\n"
            "  groups:history   – read private channel message history\n"
            "  users:read       – fetch user list\n"
            "  emoji:read       – fetch custom workspace emoji\n"
            "  files:read       – download file attachments\n"
            "  metadata.message:read – include structured message metadata in history"
        )

    if args.channel and args.skip_channel:
        parser.error("--channel and --skip-channel are mutually exclusive.")

    if args.list_channels:
        exporter = SlackExporter(token=args.token)
        denylist = set(args.skip_channel) if args.skip_channel else None
        channels = exporter.fetch_channels(denylist=denylist)
        print(f"{'ID':<12} {'TYPE':<8} {'MEMBER':<11} {'STATUS':<9} NAME")
        print("-" * 70)
        for ch in sorted(channels, key=lambda c: c["name"]):
            ch_type  = "private"    if ch.get("is_private")  else "public"
            member   = "member"     if ch.get("is_member")   else "non-member"
            status   = "archived"   if ch.get("is_archived") else "active"
            print(f"{ch['id']:<12} {ch_type:<8} {member:<11} {status:<9} #{ch['name']}")
        print(f"\n{len(channels)} channel(s)")
        return

    if args.output and args.backup_dir:
        parser.error("--output and --backup-dir are mutually exclusive.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.backup_dir:
        output_dir = str(Path(args.backup_dir) / f"slack_export_{timestamp}")
    else:
        output_dir = args.output or f"slack_export_{timestamp}"
    exporter = SlackExporter(
        token=args.token,
        output_dir=output_dir,
        download_files=not args.no_files,
    )
    allowlist = set(args.channel) if args.channel else None
    denylist = set(args.skip_channel) if args.skip_channel else None
    exporter.export(allowlist=allowlist, denylist=denylist)

    if args.html:
        try:
            from slack_html import SlackHTMLRenderer
        except ImportError:
            tqdm.write("    [warn] slack_html.py not found — skipping HTML generation.")
        else:
            renderer = SlackHTMLRenderer(
                export_dir=exporter.out,
                download_avatars=not args.no_avatars,
            )
            renderer.render()
            print(f"  HTML      : {exporter.out / 'html' / 'index.html'}")


if __name__ == "__main__":
    main()
