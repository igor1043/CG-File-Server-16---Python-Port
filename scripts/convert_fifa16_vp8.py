"""Convert a source video into a FIFA 16 VP8/Vorbis WebM movie.

FFmpeg is used as the encoder. The output container is explicitly WebM even
when the destination uses FIFA's ``.vp8`` filename extension.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def find_tool(name: str, explicit: str | None) -> str:
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"Executable not found: {candidate}")
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"{name} was not found on PATH. Install FFmpeg or pass --{name} with its path."
    )


def probe(ffprobe: str, media: Path) -> dict:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(media)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a high-quality FIFA 16 VP8/Vorbis .vp8 movie using FFmpeg/libvpx."
    )
    parser.add_argument("input", type=Path, help="Source video")
    parser.add_argument("output", type=Path, help="Destination .vp8 path")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg.exe (otherwise searched on PATH)")
    parser.add_argument("--ffprobe", help="Path to ffprobe.exe (otherwise inferred/searched)")
    parser.add_argument("--width", type=int, default=1920, help="Output width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Output height (default: 1080)")
    parser.add_argument("--fps", default="2997/100", help="Output FPS (default: 2997/100, matching FIFA 16 movies)")
    parser.add_argument("--crf", type=int, default=4, help="VP8 constant-quality level, 0-63 (default: 4)")
    parser.add_argument("--cpu-used", type=int, default=2, help="VP8 encoder speed preset, 0-8 (default: 2)")
    parser.add_argument(
        "--video-bitrate",
        "--max-bitrate",
        dest="video_bitrate",
        default="8000k",
        help="VP8 bitrate target for constrained-quality encoding (default: 8000k).",
    )
    parser.add_argument("--audio-quality", type=int, default=6, help="Vorbis quality, -1.0 to 10.0 (default: 6)")
    parser.add_argument("--audio-rate", type=int, default=44100, help="Output audio sample rate (default: 44100 Hz)")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing destination")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Input video does not exist: {source}")
    if output.suffix.lower() != ".vp8":
        parser.error("Output filename must end in .vp8")
    if args.width <= 0 or args.height <= 0:
        parser.error("Output width and height must be positive")
    if not 0 <= args.crf <= 63:
        parser.error("CRF must be between 0 and 63")
    if not 0 <= args.cpu_used <= 8:
        parser.error("CPU-used must be between 0 and 8")
    if not -1.0 <= args.audio_quality <= 10.0:
        parser.error("Vorbis quality must be between -1.0 and 10.0")
    if output.exists() and not args.overwrite:
        parser.error(f"Destination already exists: {output} (use --overwrite to replace it)")

    ffmpeg = find_tool("ffmpeg", args.ffmpeg)
    if args.ffprobe:
        ffprobe = find_tool("ffprobe", args.ffprobe)
    else:
        sibling_probe = Path(ffmpeg).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        ffprobe = str(sibling_probe) if sibling_probe.is_file() else find_tool("ffprobe", None)

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.stem}.partial.vp8")
    if partial.exists():
        parser.error(f"Temporary output already exists: {partial}; remove it or choose another path")

    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-n",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-map_metadata",
        "-1",
        "-map_metadata:s",
        "-1",
        "-map_chapters",
        "-1",
        "-vf",
        f"scale={args.width}:{args.height}:flags=lanczos,fps={args.fps},format=yuv420p",
        "-c:v",
        "libvpx",
        "-deadline",
        "good",
        "-cpu-used",
        str(args.cpu_used),
        "-crf",
        str(args.crf),
        "-b:v",
        args.video_bitrate,
        "-c:a",
        "libvorbis",
        "-q:a",
        str(args.audio_quality),
        "-ar",
        str(args.audio_rate),
        "-ac",
        "2",
        "-f",
        "webm",
        str(partial),
    ]

    try:
        subprocess.run(command, check=True)
        details = probe(ffprobe, partial)
        streams = details.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if not video or video.get("codec_name") != "vp8":
            raise RuntimeError("FFprobe did not confirm a VP8 video stream")
        if (video.get("width"), video.get("height")) != (args.width, args.height):
            raise RuntimeError("Encoded dimensions do not match the requested dimensions")
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if audio and audio.get("codec_name") != "vorbis":
            raise RuntimeError("FFprobe did not confirm a Vorbis audio stream")
        if "matroska" not in details.get("format", {}).get("format_name", ""):
            raise RuntimeError("FFprobe did not confirm a WebM/Matroska container")
        if output.exists() and args.overwrite:
            output.unlink()
        partial.replace(output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    details = probe(ffprobe, output)
    video = next(stream for stream in details["streams"] if stream.get("codec_type") == "video")
    audio = next((stream for stream in details["streams"] if stream.get("codec_type") == "audio"), None)
    print(f"Created: {output}")
    print(f"Video: VP8 {video['width']}x{video['height']} at {video.get('avg_frame_rate', 'unknown')} fps")
    print(f"Audio: {audio['codec_name'] if audio else 'none'}")
    print(f"Container: {details['format'].get('format_name', 'unknown')}")
    print(f"Size: {output.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
