"""The files a remote display downloads from the game: the PuP Pack's playlists of the display's screens, read in place.

    media = topper_media(pack_dir, screens, triggers)       # {"Folder/File.mp4": absolute path}
    RemoteServer(..., media=media)

The playlists are the ones the screens play: each screen's default background (screens.pup) and every active
triggers.pup row on those screens, the same choice the game's own PuP player makes. `screens` is what the game's pupfiles
module returns for screens.pup ({number: {"playlist", ...}}), `triggers` its rows (objects with screen, active,
playlist). Nothing is copied, converted or generated: the server streams the pack's own files. Files the Pi's decoder
cannot play (not H.264, above 1920x1080 or 30 fps, 10-bit) are a bundle add-on made once at build time, not a runtime step.
"""
import os

TOPPER_SCREENS = (13, 14)                 # the topper's underlay and pop-up layer in the packs we know
FILES = (".mp4", ".m4v", ".mov", ".avi", ".wmv", ".webm", ".mkv", ".f4v", ".png", ".jpg", ".jpeg")


def playlists_of(screens, triggers, numbers=TOPPER_SCREENS):
    lists = {row["playlist"].lower() for num, row in screens.items() if num in numbers and row.get("playlist")}
    lists |= {t.playlist.lower() for t in triggers if t.screen in numbers and t.active and t.playlist}
    return lists


def topper_media(pack_dir, screens, triggers, numbers=TOPPER_SCREENS):
    """{pack path ("Folder/File.mp4"): absolute path} of the media files in those playlist folders; {} without a pack."""
    wanted = playlists_of(screens, triggers, numbers)
    files = {}
    if not os.path.isdir(pack_dir):
        return files
    for folder in sorted(os.listdir(pack_dir)):
        path = os.path.join(pack_dir, folder)
        if folder.lower() in wanted and os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if os.path.isfile(os.path.join(path, name)) and name.lower().endswith(FILES):
                    files[folder + "/" + name] = os.path.join(path, name)
    return files
