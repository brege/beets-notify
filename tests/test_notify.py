from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import apprise
import pytest
from beets import plugins
from beets.library import Album
from beets.util.artresizer import ArtResizer
from PIL import Image

from beetsplug.notify import NotifyPlugin, generate_collage, resize_artwork

if TYPE_CHECKING:
    from collections.abc import Iterator

    from beets.test.helper import PluginTestHelper


@pytest.fixture
def beets_helper() -> Iterator[PluginTestHelper]:
    # Beets' helper narrows beetsplug.__path__, so import it after this plugin.
    from beets.test.helper import PluginTestHelper

    with PluginTestHelper() as helper:
        yield helper


class FakeApprise:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.notifications: list[dict[str, object]] = []

    def add(self, url: str) -> bool:
        self.urls.append(url)
        return True

    def __len__(self) -> int:
        return len(self.urls)

    def notify(self, **kwargs: object) -> bool:
        self.notifications.append(kwargs)
        return True


@pytest.mark.usefixtures("beets_helper")
class TestNotifyPlugin:
    def album(self, art_path: os.PathLike[str] | None = None) -> Album:
        return Album(
            albumartist="Artist",
            album="Album",
            year=2026,
            artpath=os.fsencode(art_path) if art_path else None,
        )

    def test_generate_collage_skips_invalid_artwork(
        self, tmp_path: Path
    ) -> None:
        invalid_path = tmp_path / "invalid.jpg"
        invalid_path.write_text("not an image")
        valid_path = tmp_path / "valid.png"
        Image.new("RGB", (20, 10), "blue").save(valid_path)

        collage = generate_collage([invalid_path, valid_path])

        assert collage is not None
        with Image.open(collage) as image:
            assert image.size == (600, 300)
        Path(collage).unlink()

    def test_build_message_uses_first_artwork_without_collage(
        self, tmp_path: Path
    ) -> None:
        art_path = tmp_path / "cover.png"
        Image.new("RGB", (20, 10), "blue").save(art_path)
        plugin = NotifyPlugin()
        plugin.config["collage"].set(False)

        title, body, artwork = plugin.build_message([self.album(art_path)])

        assert title == "Beets: 1 album imported"
        assert body == "Artist - Album (2026)"
        assert artwork is not None
        assert artwork == str(art_path)

    def test_build_message_preserves_native_path_bytes(
        self, tmp_path: Path
    ) -> None:
        source_path = tmp_path / "source.png"
        Image.new("RGB", (20, 10), "blue").save(source_path)
        art_bytes = os.path.join(os.fsencode(tmp_path), b"cover-\xff.png")
        os.rename(os.fsencode(source_path), art_bytes)
        plugin = NotifyPlugin()
        plugin.config["collage"].set(False)

        _, _, artwork = plugin.build_message([Album(artpath=art_bytes)])

        assert artwork is not None
        assert os.fsencode(artwork) == art_bytes

    def test_resize_artwork_uses_shared_resizer(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        art_path = tmp_path / "cover.png"
        Image.new("RGB", (20, 10), "blue").save(art_path)

        def fake_resize(
            maxwidth: int,
            path_in: bytes,
            path_out: bytes | None = None,
            quality: int = 0,
            max_filesize: int = 0,
        ) -> bytes:
            assert path_out is not None
            return path_out

        monkeypatch.setattr(ArtResizer.shared, "resize", fake_resize)

        artwork = resize_artwork(art_path, max_filesize=1)

        assert Path(artwork).exists()
        Path(artwork).unlink()
        assert art_path.exists()

    def test_notification_removes_generated_collage(
        self, monkeypatch, tmp_path: Path, beets_helper: PluginTestHelper
    ) -> None:
        art_path = tmp_path / "cover.png"
        Image.new("RGB", (20, 10), "blue").save(art_path)
        fake_apprise = FakeApprise()
        monkeypatch.setattr(apprise, "Apprise", lambda: fake_apprise)
        plugin = NotifyPlugin()
        plugin.config["apprise_urls"].set(["json://example.invalid"])

        plugin.send_notification(beets_helper.lib, [self.album(art_path)])

        attached = fake_apprise.notifications[0]["attach"]
        assert isinstance(attached, str)
        attached_path = Path(attached)
        assert not attached_path.exists()
        assert art_path.exists()

    def test_beets_events_dispatch_notification(
        self, monkeypatch, beets_helper: PluginTestHelper
    ) -> None:
        fake_apprise = FakeApprise()
        monkeypatch.setattr(apprise, "Apprise", lambda: fake_apprise)
        plugin = NotifyPlugin()
        plugin.config["apprise_urls"].set(["json://example.invalid"])
        plugin.config["artwork"].set(False)
        album = self.album()

        plugins.send("album_imported", lib=beets_helper.lib, album=album)
        plugins.send("cli_exit", lib=beets_helper.lib)

        assert plugin.imported_albums == [album]
        assert fake_apprise.urls == ["json://example.invalid"]
        assert fake_apprise.notifications == [
            {
                "title": "Beets: 1 album imported",
                "body": "Artist - Album (2026)",
            }
        ]
