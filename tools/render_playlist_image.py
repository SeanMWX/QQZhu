"""
Generate a playlist long image from a full background and a playlist text file.

Steps:
1) Split the full background into head/content/end parts (like split_bg.py).
2) Render the playlist onto the combined background (like create_playlist_image.py).

Example:
python tools/render_playlist_image.py ^
    --input-image sample.png ^
    --playlist tools/create_playlist_image/playlist.txt ^
    --content-start 120 ^
    --end-start 1560 ^
    --output-image playlist.png
"""
import argparse
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SPLIT_DIR = THIS_DIR / "create_playlist_image"
if str(SPLIT_DIR) not in sys.path:
    sys.path.append(str(SPLIT_DIR))

from create_playlist_image import create_playlist_image  # type: ignore
from split_bg import split_image  # type: ignore


def main():
    parser = argparse.ArgumentParser(description="Split background then render playlist long image.")
    parser.add_argument("--input-image", required=True, type=Path, help="Full background image (e.g., sample.png).")
    parser.add_argument("--playlist", required=True, type=Path, help="Text file with one song name per line.")
    parser.add_argument("--content-start", required=True, type=int, help="Y position where the content part begins.")
    parser.add_argument("--end-start", required=True, type=int, help="Y position where the end part begins.")
    parser.add_argument("--output-image", type=Path, default=Path("playlist.png"), help="Output playlist image path.")
    parser.add_argument("--font-path", type=Path, default=None, help="Optional font file path.")
    parser.add_argument(
        "--max-chars-per-line",
        type=int,
        default=35,
        help="Max characters per rendered line before wrapping.",
    )
    parser.add_argument(
        "--max-songs-per-line",
        type=int,
        default=6,
        help="Max song names per line before wrapping.",
    )
    args = parser.parse_args()

    bg_dir = args.output_image.parent if args.output_image.parent != Path("") else Path.cwd()
    head_path, content_path, end_path = split_image(
        src=args.input_image,
        content_start=args.content_start,
        end_start=args.end_start,
        output_dir=bg_dir,
    )

    create_playlist_image(
        input_txt=args.playlist,
        head_img_path=head_path,
        content_img_path=content_path,
        end_img_path=end_path,
        output_image=args.output_image,
        font_path=args.font_path,
        max_chars_per_line=args.max_chars_per_line,
        max_songs_per_line=args.max_songs_per_line,
    )


if __name__ == "__main__":
    main()
