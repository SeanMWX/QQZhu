"""
Generate multiple playlist images using a fixed background and a text region.

Given:
- A background image (e.g., sample.png)
- A playlist text file (one song name per line)
- A rectangle region (x1,y1,x2,y2) to render text

The script paginates song names into as many images as needed.

Example:
python tools/render_playlist_pages.py ^
  --background tools/create_playlist_image/sample.png ^
  --playlist tools/create_playlist_image/playlist.txt ^
  --rect 60,300,1100,1700 ^
  --output-prefix playlist_page
"""
import argparse
import math
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont


def pick_font(font_path: Optional[Path], size: int) -> ImageFont.FreeTypeFont:
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    try_fonts = [
        "msyhl.ttc",
        "SourceHanSansSC-Light.otf",
        "msyh.ttc",
        "simsun.ttc",
        "STHeiti Light.ttc",
    ]
    for tf in try_fonts:
        try:
            return ImageFont.truetype(tf, size)
        except Exception:
            continue
    font = ImageFont.load_default()
    font.size = size
    return font


def wrap_song_names(names: List[str], max_chars_per_line: int, max_songs_per_line: int) -> List[str]:
    lines: List[str] = []
    current: List[str] = []
    current_chars = 0
    for name in names:
        name_len = len(name)
        if current and (current_chars + name_len > max_chars_per_line or len(current) >= max_songs_per_line):
            lines.append("  ".join(current))
            current = []
            current_chars = 0
        current.append(name)
        current_chars += name_len + 2
    if current:
        lines.append("  ".join(current))
    return lines


def parse_rect(rect_str: str) -> Tuple[int, int, int, int]:
    parts = rect_str.split(",")
    if len(parts) != 4:
        raise ValueError("rect must be in format x1,y1,x2,y2")
    try:
        x1, y1, x2, y2 = map(int, parts)
    except Exception:
        raise ValueError("rect values must be integers")
    if not (x1 < x2 and y1 < y2):
        raise ValueError("rect must satisfy x1 < x2 and y1 < y2")
    return x1, y1, x2, y2


def render_pages(
    background: Path,
    playlist: Path,
    rect: Tuple[int, int, int, int],
    output_prefix: Path,
    font_path: Optional[Path],
    font_size: int,
    max_chars_per_line: int,
    max_songs_per_line: int,
    line_height: int,
) -> List[Path]:
    img = Image.open(background).convert("RGB")
    x1, y1, x2, y2 = rect
    width, height = img.size
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("rect is outside background bounds")

    with open(playlist, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    if not names:
        raise ValueError("playlist is empty")

    lines = wrap_song_names(names, max_chars_per_line, max_songs_per_line)
    lines_per_page = max(1, (y2 - y1) // line_height)
    pages = math.ceil(len(lines) / lines_per_page)

    # pick text color based on region background
    sample_x = min(max(x1 + 5, 0), width - 1)
    sample_y = min(max(y1 + 5, 0), height - 1)
    bg_color = img.getpixel((sample_x, sample_y))
    text_color = (30, 30, 30) if sum(bg_color) > 382 else (240, 240, 240)
    shadow_color = (
        (max(bg_color[0] - 30, 0), max(bg_color[1] - 30, 0), max(bg_color[2] - 30, 0))
        if sum(bg_color) > 382
        else (0, 0, 0)
    )

    font = pick_font(font_path, font_size)

    output_files: list[Path] = []
    for page in range(pages):
        start = page * lines_per_page
        end = start + lines_per_page
        page_lines = lines[start:end]

        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        y = y1
        for line in page_lines:
            text_w, text_h = draw.textsize(line, font=font)
            text_y = y + (line_height - text_h) // 2
            draw.text((x1 + 2, text_y + 2), line, font=font, fill=shadow_color)
            draw.text((x1, text_y), line, font=font, fill=text_color)
            y += line_height

        out_path = output_prefix.parent / f"{output_prefix.name}_{page+1:02d}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, quality=95)
        output_files.append(out_path)
    return output_files


def main():
    parser = argparse.ArgumentParser(description="Render playlist into paginated images within a rectangle.")
    parser.add_argument("--background", required=True, type=Path, help="Background image (e.g., sample.png).")
    parser.add_argument("--playlist", required=True, type=Path, help="Playlist text file (one song per line).")
    parser.add_argument("--rect", required=True, help="Text region x1,y1,x2,y2 (e.g., 60,300,1100,1700).")
    parser.add_argument("--output-prefix", type=Path, default=Path("playlist_page"), help="Output file prefix.")
    parser.add_argument("--font-path", type=Path, default=None, help="Optional font file.")
    parser.add_argument("--font-size", type=int, default=38, help="Font size.")
    parser.add_argument("--max-chars-per-line", type=int, default=35, help="Max characters per line.")
    parser.add_argument("--max-songs-per-line", type=int, default=6, help="Max song names per line.")
    parser.add_argument("--line-height", type=int, default=80, help="Line height in pixels.")
    args = parser.parse_args()

    rect = parse_rect(args.rect)
    outputs = render_pages(
        background=args.background,
        playlist=args.playlist,
        rect=rect,
        output_prefix=args.output_prefix,
        font_path=args.font_path,
        font_size=args.font_size,
        max_chars_per_line=args.max_chars_per_line,
        max_songs_per_line=args.max_songs_per_line,
        line_height=args.line_height,
    )
    print("Generated files:")
    for p in outputs:
        print(f"- {p}")


if __name__ == "__main__":
    main()
