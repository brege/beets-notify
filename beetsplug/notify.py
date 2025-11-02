# Copyright (c) 2025 Wyatt Brege

# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

"""Sends notifications on import completion via Apprise."""

import os
import tempfile

import apprise

from beets.plugins import BeetsPlugin
from beets.util.artresizer import ArtResizer


def resize_artwork(art_path, max_filesize=0):
    """Return path to resized artwork, or original if no resize needed.

    The new extension must not contain a leading dot.
    """
    current_size = os.path.getsize(art_path)

    if max_filesize == 0 or current_size <= max_filesize:
        return art_path

    # Resize the image to meet filesize constraint.
    resizer = ArtResizer()
    _, ext = os.path.splitext(art_path)
    tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    resized_path = resizer.resize(
        maxwidth=1000,
        path_in=art_path,
        path_out=tmp_file.name,
        max_filesize=max_filesize,
    )

    return resized_path


class NotifyPlugin(BeetsPlugin):
    """Send notifications when imports complete."""

    imported_albums = []

    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "apprise_urls": [],
                "truncate": 3,
                "body_maxlength": 1024,
                "artwork": True,
                "artwork_maxsize": 0,  # 0 = use apprise's per-service limits
                "show_first_art": True,
            }
        )

        self.config["apprise_urls"].redact = True

        self.register_listener("album_imported", self.album_imported)
        self.register_listener("cli_exit", self.notify_on_cli_exit)

    def album_imported(self, lib, album):
        """Collect imported albums for batch notification."""
        self.imported_albums.append(album)

    def notify_on_cli_exit(self, lib):
        """Send notification when CLI exits if albums were imported."""
        if not self.imported_albums:
            return

        self._log.debug(
            "sending notification for {} album(s)", len(self.imported_albums)
        )
        self.send_notification(lib, self.imported_albums)

    def send_notification(self, lib, imported_albums):
        """Send notification via Apprise."""
        urls = self.config["apprise_urls"].as_str_seq()

        if not urls:
            self._log.debug("no apprise URLs configured")
            return

        # Build notification content.
        title, body, artwork_path = self.build_message(imported_albums)

        # Initialize Apprise and add URLs.
        apobj = apprise.Apprise()
        for url in urls:
            if not apobj.add(url):
                self._log.warning("failed to add apprise URL")

        if len(apobj) == 0:
            self._log.error("no valid apprise URLs configured")
            return

        # Send notification.
        try:
            if artwork_path:
                success = apobj.notify(title=title, body=body, attach=artwork_path)
            else:
                success = apobj.notify(title=title, body=body)

            if success:
                self._log.info("notification sent to {} service(s)", len(apobj))
            else:
                self._log.error("notification failed")

        except Exception as e:
            self._log.error("notification error: {}", e)

    def build_message(self, imported_albums):
        """Build notification title, body, and optional artwork path."""
        truncate = self.config["truncate"].get(int)
        max_albums = min(len(imported_albums), truncate)

        # Build title.
        album_word = "album" if len(imported_albums) == 1 else "albums"
        title = f"Beets: {len(imported_albums)} {album_word} imported"

        # Build body with album list.
        body_lines = []
        artwork_path = None

        for i, album in enumerate(imported_albums[:max_albums]):
            body_lines.append(f"{album.albumartist} - {album.album} ({album.year})")

            # Get artwork from first album if enabled.
            if (
                i == 0
                and self.config["artwork"]
                and self.config["show_first_art"]
                and album.artpath
            ):
                try:
                    if isinstance(album.artpath, bytes):
                        art_path = album.artpath.decode("utf-8")
                    else:
                        art_path = album.artpath

                    # Downsize artwork if too large.
                    max_size = self.config["artwork_maxsize"].get(int)
                    artwork_path = resize_artwork(art_path, max_filesize=max_size)

                except Exception as e:
                    self._log.debug("failed to process artwork: {}", e)

        body = "\n".join(body_lines)

        # Add truncation message.
        if len(imported_albums) > max_albums:
            remaining = len(imported_albums) - max_albums
            body += f"\n...and {remaining} more"

        # Truncate body if too long.
        max_length = self.config["body_maxlength"].get(int)
        if len(body) > max_length:
            body = body[: max_length - 3] + "..."

        return title, body, artwork_path
