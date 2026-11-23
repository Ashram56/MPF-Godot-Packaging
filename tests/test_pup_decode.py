"""tools/pup/pup_decode.py reads a PuP Pack from a folder or a zip and matches its DMD captures with a game's
frames as PinUP Player does. The real run on the Tron pack is in agents/pup_pack.md ("Checking a run")."""
import csv
import io
import json
import os
import sys
import zipfile

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "pup"))
import pup_decode  # noqa: E402

PURPLE = (253, 0, 253)


def bmp(lit, rect=(10, 4, 30, 12)):
    """A 128x32 capture: a purple rectangle around `rect`, the `lit` dots red."""
    image = Image.new("RGB", (128, 32))
    x0, y0, x1, y1 = rect
    for x in range(x0, x1 + 1):
        image.putpixel((x, y0), PURPLE)
        image.putpixel((x, y1), PURPLE)
    for y in range(y0, y1 + 1):
        image.putpixel((x0, y), PURPLE)
        image.putpixel((x1, y), PURPLE)
    for xy in lit:
        image.putpixel(xy, (255, 40, 0))
    out = io.BytesIO()
    image.save(out, "BMP")
    return out.getvalue()


def gif(path, frames):
    images = []
    for lit in frames:
        image = Image.new("L", (128, 32))
        for xy in lit:
            image.putpixel(xy, 200)
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:])


@pytest.fixture
def pack_zip(tmp_path):
    path = tmp_path / "pack.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("PUPVideos/mygame/triggers.pup",
                   "ID,Active,Descript,Trigger,ScreenNum,PlayList,PlayFile,Volume,Priority,Length,Counter,"
                   "RestSeconds,Loop,Defaults\n"
                   "1,1,\"**** STARTUP ****\",,,,,,,,,,,0\n"
                   "2,1,Boot,D0=1,2,Background,,,,,,,SetBG,0\n"
                   "3,1,Jackpot,D1,12,Jackpot,,,5,,,3,,0\n"
                   "4,1,Target,W7=1,14,Letters,T.mp4,,3,,,,,0\n"
                   "5,1,Combo,\"W11=1,L35=1\",12,Mystery,,,3,,,,,0\n")
        z.writestr("PUPVideos/mygame/playlists.pup",
                   "ScreenNum,Folder,Des,AlphaSort,RestSeconds,Volume,Priority\n0,Jackpot,,1,2,100,0\n")
        z.writestr("PUPVideos/mygame/screens.pup",
                   "ScreenNum,ScreenDes,PlayList,PlayFile,Loopit,Active,Priority,CustomPos\n"
                   "2,Backglass,Background,bg.mp4,0,ForceBack,90,\n")
        z.writestr("PUPVideos/mygame/Jackpot/Jackpot1.mp4", b"x")
        z.writestr("PUPVideos/mygame/Jackpot/Jackpot2.mp4", b"x")
        z.writestr("PUPVideos/mygame/PupCapture/1.bmp", bmp([(12, 6), (13, 6), (14, 7)]))
        z.writestr("PUPVideos/mygame/PupCapture/2.bmp", bmp([(20, 8)]))
        z.writestr("PUPVideos/readme.txt", "not the pack")
    return path


def test_decode_from_zip(pack_zip, tmp_path):
    pack = pup_decode.Pack(str(pack_zip))
    assert "triggers.pup" in pack.names and "readme.txt" not in pack.names
    data = pup_decode.decode(pack)
    assert [t["id"] for t in data["triggers"]] == [1, 2, 3, 4, 5]       # a section header is a row too
    assert data["triggers"][0]["terms"] == []
    assert data["triggers"][4]["terms"] == [["W", 11, 1], ["L", 35, 1]]
    assert data["playlists"][0]["files"] == ["Jackpot1.mp4", "Jackpot2.mp4"]
    assert data["captures"]["1"]["rect"] == [10, 4, 30, 12] and data["captures"]["1"]["lit_dots"] == 3
    assert data["summary"]["unused_captures"] == [2]
    assert data["summary"]["codes"] == {"D": 2, "W": 2, "L": 1}
    out = tmp_path / "pack.json"
    assert pup_decode.main(["decode", str(pack_zip), str(out)]) == 0
    assert json.loads(out.read_text())["summary"]["captures"] == 2


def test_match_and_map(pack_zip, tmp_path):
    frames = tmp_path / "frames"
    (frames / "deff_7_jackpot").mkdir(parents=True)
    (frames / "deff_9_other").mkdir()
    (frames / "library" / "anim_3").mkdir(parents=True)
    gif(str(frames / "deff_7_jackpot" / "a.gif"), [[(50, 20)], [(12, 6), (13, 6), (14, 7), (90, 30)]])
    gif(str(frames / "deff_9_other" / "a.gif"), [[(12, 6)]])
    gif(str(frames / "library" / "anim_3" / "a.gif"), [[(20, 8)]])
    owners = tmp_path / "owners.csv"
    with open(owners, "w", newline="") as f:
        csv.writer(f).writerows([["pattern", "id"], ["library/anim_3/", "11"]])
    report, ymap = tmp_path / "report.md", tmp_path / "map.yaml"
    assert pup_decode.main(["match", str(pack_zip), str(report), "--frames", str(frames / "**" / "*.gif"),
                            "--owners", str(owners), "--event", "game_deff_{id}", "--map", str(ymap)]) == 0
    text = report.read_text()
    assert "| 1 | 3 | 10,4-30,12 | 100% | 7 |" in text      # a dot outside the rectangle does not count
    assert "| 2 | - | 10,4-30,12 | 100% | 11 |" in text     # owned through --owners
    lines = ymap.read_text().splitlines()
    assert "  1: [game_deff_7]  # 100%" in lines
    assert "  7: sw7       # rename to the game's switch name" in lines
    assert any(line.startswith("  5: []   # W11=1,L35=1") for line in lines)


def test_capture_without_a_rectangle_compares_the_whole_frame():
    image = Image.new("RGB", (128, 32))
    for xy in ((0, 0), (127, 31), (64, 16)):
        image.putpixel(xy, (255, 69, 0))
    out = io.BytesIO()
    image.save(out, "BMP")
    cap = pup_decode.capture(out.getvalue())
    assert cap["rect"] == [0, 0, 127, 31]
    assert bin(cap["lit"]).count("1") == 3


def test_scaled_frames_and_hex_ids(pack_zip, tmp_path):
    """A 2x capture (T2's 256x64 GIFs) is read as 128x32; --id-text keeps hex ids with their zeros (deff04)."""
    frames = tmp_path / "deffs"
    frames.mkdir()
    image = Image.new("L", (256, 64))
    for x, y in ((12, 6), (13, 6), (14, 7)):
        for dx in (0, 1):
            for dy in (0, 1):
                image.putpixel((2 * x + dx, 2 * y + dy), 200)
    image.save(str(frames / "deff0a.gif"))
    report, ymap = tmp_path / "report.md", tmp_path / "map.yaml"
    try:
        assert pup_decode.main(["match", str(pack_zip), str(report), "--frames", str(frames / "deff*.gif"),
                                "--id-regex", r"deff([0-9a-f]{2})", "--id-text", "--event", "t2_deff_{id}",
                                "--map", str(ymap)]) == 0
    finally:
        pup_decode.KEEP_ID_TEXT = False
    assert "  1: [t2_deff_0a]  # 100%" in ymap.read_text().splitlines()
