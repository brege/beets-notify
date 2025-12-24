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
from PIL import Image, ImageDraw, ImageFont

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


def generate_collage(art_paths, max_filesize=0):
    """Generate a grid collage from album artwork paths.

    Grid layout progression:
    - 1 image: 1x1
    - 2 images: 1x2
    - 3-4 images: 2x2
    - 5-6 images: 2x3
    - 7-9 images: 3x3
    - 10+ images: 3x3 with "+N more" overlay on last cell

    Returns path to collage image or None if no valid images.
    """
    if not art_paths:
        return None

    # Determine grid dimensions and number of images to show.
    num_images = len(art_paths)
    if num_images == 1:
        cols, rows = 1, 1
        images_to_show = 1
    elif num_images == 2:
        cols, rows = 2, 1
        images_to_show = 2
    elif num_images <= 4:
        cols, rows = 2, 2
        images_to_show = num_images
    elif num_images <= 6:
        cols, rows = 3, 2
        images_to_show = num_images
    elif num_images <= 9:
        cols, rows = 3, 3
        images_to_show = num_images
    else:
        cols, rows = 3, 3
        images_to_show = 8

    cell_size = 300
    canvas_width = cols * cell_size
    canvas_height = rows * cell_size

    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")

    loaded_count = 0
    for i in range(min(images_to_show, len(art_paths))):
        art_path = art_paths[i]

        try:
            resized_path = resize_artwork(art_path, max_filesize=max_filesize)
            img = Image.open(resized_path)

            img.thumbnail((cell_size, cell_size), Image.Resampling.LANCZOS)

            row = i // cols
            col = i % cols
            x = col * cell_size
            y = row * cell_size

            canvas.paste(img, (x, y))
            loaded_count += 1

        except Exception:
            pass

    if loaded_count == 0:
        return None

    # Add "+N more" overlay if necessary.
    if num_images > images_to_show:
        remaining = num_images - images_to_show
        overlay_idx = images_to_show
        row = overlay_idx // cols
        col = overlay_idx % cols
        x = col * cell_size
        y = row * cell_size

        draw = ImageDraw.Draw(canvas)
        overlay = Image.new("RGBA", (cell_size, cell_size), (200, 200, 200, 180))
        canvas.paste(overlay, (x, y), overlay)

        text = f"+{remaining} more"
        try:
            font = ImageFont.load_default(size=40)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x + (cell_size - text_width) // 2
            text_y = y + (cell_size - text_height) // 2
            draw.text((text_x, text_y), text, fill="black", font=font)
        except Exception:
            pass

    # Save collage.
    tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    canvas.save(tmp_file.name, "PNG")

    return tmp_file.name


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
                "collage": True,
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

        body = "\n".join(body_lines)

        # Add truncation message.
        if len(imported_albums) > max_albums:
            remaining = len(imported_albums) - max_albums
            body += f"\n...and {remaining} more"

        # Truncate body if too long.
        max_length = self.config["body_maxlength"].get(int)
        if len(body) > max_length:
            body = body[: max_length - 3] + "..."

        # Collect artwork and handle based on collage setting.
        if self.config["artwork"]:
            if self.config["collage"]:
                art_paths = []
                for album in imported_albums:
                    if album.artpath:
                        try:
                            if isinstance(album.artpath, bytes):
                                art_path = album.artpath.decode("utf-8")
                            else:
                                art_path = album.artpath
                            art_paths.append(art_path)
                        except Exception as e:
                            self._log.debug("failed to process artwork: {}", e)

                if art_paths:
                    max_size = self.config["artwork_maxsize"].get(int)
                    try:
                        artwork_path = generate_collage(art_paths, max_filesize=max_size)
                    except Exception as e:
                        self._log.debug("failed to generate collage: {}", e)
            else:
                # Collage disabled, use first album's artwork.
                for album in imported_albums:
                    if album.artpath:
                        try:
                            if isinstance(album.artpath, bytes):
                                art_path = album.artpath.decode("utf-8")
                            else:
                                art_path = album.artpath
                            max_size = self.config["artwork_maxsize"].get(int)
                            artwork_path = resize_artwork(art_path, max_filesize=max_size)
                            break
                        except Exception as e:
                            self._log.debug("failed to process artwork: {}", e)

        return title, body, artwork_path
