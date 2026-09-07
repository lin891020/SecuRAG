"""Give the silent README demos a voice and burned-in subtitles.

    python3 scripts/narrate_demo.py --check              # will every line fit?
    python3 scripts/narrate_demo.py --frames d1.5        # look at a cue's window
    python3 scripts/narrate_demo.py --tts                # synthesise, and listen back
    python3 scripts/narrate_demo.py --build              # cut, subtitle, mix

The recordings already exist and cannot be re-timed, which is the whole problem:
a written line either fits the seconds it describes or it does not. Where it
does not, that stretch of video is slowed until it does -- the picture during
those stretches is a model streaming an answer, so it barely moves anyway --
and every later timestamp is remapped through the change.

Reuses ~/Projects/video_transfer for the voice rather than reaching for a TTS
library directly, the same way ~/Projects/aoi-agent/scripts/demo_record.py
does: `source env.sh local`, `get_tts_backend`, `dubscript.to_dub_text`, and
each finished line listened back through Whisper before it is trusted.

macOS: the subtitle filter needs the Homebrew ffmpeg-full build. The ffmpeg on
PATH is compiled without it and will produce a video with no subtitles and no
error.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_script import DEMOS, IDENTIFIERS, WORDS_PER_SECOND, Cue, Demo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo"
BUILD = OUT / "build"
VIDEO_TRANSFER = Path.home() / "Projects" / "video_transfer"

FFMPEG = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FFPROBE = "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"

OUT_W = 1920
FPS = 30
KOKORO_VOICE = "af_heart"

#: libass lays a subtitle out against a 288-line virtual script, so a font size
#: of 13 is this many pixels on a frame of a given height. The band has to be
#: tall enough for the longest cue at that size.
ASS_FONT_SIZE = 13
ASS_VIRTUAL_HEIGHT = 288
LINE_SPACING = 1.25
BAND_MARGIN = 12

#: How far a stretch of video may be slowed to let a line finish. Past this the
#: line is too long for what it describes and should be shortened instead --
#: slow motion on a picture that *is* moving looks broken.
MIN_SPEED = 0.35

SUBTITLE_COLUMNS = 58
"""Characters per subtitle line, measured: a 58-character line renders as one
line at `ASS_FONT_SIZE` on a 1920-wide frame. Wrapping wider than the renderer
does means libass breaks the line again, and a subtitle written as two lines
arrives as three -- which is how the band came to be too short for it."""


# --- small helpers ----------------------------------------------------------

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def duration_of(path: Path) -> float:
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).stdout.strip()
    return float(out) if out else 0.0


def dimensions_of(path: Path) -> tuple[int, int]:
    out = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0:s=x", str(path)]).stdout.strip()
    w, _, h = out.partition("x")
    return int(w), int(h)


def has_audio(path: Path) -> bool:
    return bool(run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries",
                     "stream=index", "-of", "csv=p=0", str(path)]).stdout.strip())


def require_ffmpeg() -> None:
    """Fail loudly rather than ship a video with no subtitles.

    The ffmpeg on PATH is built without the subtitle filter. It does not error
    on an unknown filter in every code path, and a missing subtitle track looks
    exactly like a subtitle track nobody noticed.
    """
    if not Path(FFMPEG).exists():
        sys.exit(f"{FFMPEG} not found. brew install ffmpeg-full")
    filters = run([FFMPEG, "-hide_banner", "-filters"]).stdout
    for needed in ("subtitles", "pad", "adelay", "amix"):
        if not re.search(rf"^\s*\S+\s+{needed}\s", filters, re.M):
            sys.exit(f"{FFMPEG} has no '{needed}' filter; it cannot build this video")


def wrap(text: str, columns: int = SUBTITLE_COLUMNS) -> list[str]:
    """Break on spaces, never exceeding `columns`.

    However many lines that takes. An earlier version capped it at two and,
    when a sentence needed three, rebalanced the words across two lines and let
    them run past the column -- so libass re-wrapped them and the subtitle
    arrived as three lines anyway, in a band sized for two.
    """
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > columns and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def band_height(picture_h: int, max_lines: int) -> int:
    """Tall enough for the longest cue, at the size libass will draw it.

    Circular by nature -- the font is sized against the finished frame, and the
    frame is the picture plus this band -- so it is solved by iterating, which
    settles within a pixel in three rounds.
    """
    band = round(picture_h * 0.12)
    for _ in range(4):
        line_px = ASS_FONT_SIZE * (picture_h + band) / ASS_VIRTUAL_HEIGHT
        band = round((max_lines * line_px * LINE_SPACING + 2 * BAND_MARGIN) / 2) * 2
    return band


def timestamp(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int(seconds % 3600 // 60), seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


# --- the timeline -----------------------------------------------------------

def estimated(cue: Cue) -> float:
    return cue.words / WORDS_PER_SECOND


def narration_dir(demo: Demo) -> Path:
    return BUILD / demo.key / "narration"


def measured(demo: Demo) -> dict[str, float] | None:
    """Real length of each synthesised line, if `--tts` has run."""
    directory = narration_dir(demo)
    wavs = {c.id: directory / f"{c.id}.wav" for c in demo.cues}
    if not all(p.exists() for p in wavs.values()):
        return None
    return {cid: duration_of(p) for cid, p in wavs.items()}


def segments(demo: Demo, durations: dict[str, float], source_length: float):
    """The source split into stretches, each with the speed it is played at.

    A cue whose line is longer than the seconds it describes slows its own
    stretch until the line fits. Everything between cues plays at speed.
    """
    segs: list[tuple[float, float, float]] = []
    cursor = 0.0
    for cue in demo.cues:
        if cue.at > cursor + 0.01:
            segs.append((cursor, cue.at, 1.0))
        need = durations.get(cue.id, estimated(cue))
        factor = 1.0 if need <= cue.window else max(MIN_SPEED, cue.window / need)
        segs.append((cue.at, cue.until, factor))
        cursor = max(cursor, cue.until)
    if cursor < source_length - 0.01:
        segs.append((cursor, source_length, 1.0))
    return segs


def remapper(segs):
    """source seconds -> output seconds, and the output length."""
    bases, clock = [], 0.0
    for start, end, factor in segs:
        bases.append((start, end, factor, clock))
        clock += (end - start) / factor
    def to_out(t: float) -> float:
        for start, end, factor, base in bases:
            if t <= end:
                return base + max(0.0, t - start) / factor
        return clock
    return to_out, clock


# --- actions ----------------------------------------------------------------

def check(demo: Demo) -> int:
    source_length = duration_of(demo.source)
    width, height = dimensions_of(demo.source)
    durations = measured(demo)
    basis = "measured" if durations else f"estimated at {WORDS_PER_SECOND} words/s"

    print(f"\nDemo {demo.key}  {demo.source.name}")
    print(f"  {width}x{height}, {source_length:.2f}s, audio={has_audio(demo.source)}")
    print(f"  line lengths {basis}\n")

    header = f"  {'cue':<7} {'window':>14} {'words':>6} {'needs':>7} {'speed':>7}  fit"
    print(header)
    print("  " + "-" * (len(header) - 2))

    problems = 0
    for cue in demo.cues:
        need = durations[cue.id] if durations else estimated(cue)
        factor = 1.0 if need <= cue.window else max(MIN_SPEED, cue.window / need)
        capped = need > cue.window and cue.window / need < MIN_SPEED
        if capped:
            problems += 1
        verdict = ("fits" if factor == 1.0
                   else f"slow {1/factor:.2f}x" if not capped
                   else f"TOO LONG by {need - cue.window / MIN_SPEED:.1f}s")
        print(f"  {cue.id:<7} {cue.at:6.1f}-{cue.until:<6.1f} {cue.window:>0.0f}s"
              f" {cue.words:>5} {need:>6.1f}s {factor:>6.2f}  {verdict}")

    for a, b in zip(demo.cues, demo.cues[1:]):
        if b.at < a.until - 0.01:
            print(f"  ! {a.id} and {b.id} overlap")
            problems += 1

    segs = segments(demo, durations or {c.id: estimated(c) for c in demo.cues}, source_length)
    _, out_length = remapper(segs)
    print(f"\n  output length {out_length:.1f}s (source {source_length:.1f}s)")
    return problems


def frames(cue_id: str, before: float, after: float, step: float) -> None:
    """Tile the frames around a cue so its start and end can be checked."""
    demo = next((d for d in DEMOS.values() if cue_id in d.cue_by_id), None)
    if demo is None:
        sys.exit(f"no cue {cue_id!r}; known: "
                 + ", ".join(c.id for d in DEMOS.values() for c in d.cues))
    cue = demo.cue_by_id[cue_id]
    start, end = max(0.0, cue.at - before), cue.until + after
    count = max(1, int((end - start) / step))
    columns = min(5, count)
    rows = (count + columns - 1) // columns
    out = BUILD / f"frames-{cue_id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{start}", "-t", f"{end - start}",
         "-i", str(demo.source),
         "-vf", f"fps=1/{step},scale=520:-2,tile={columns}x{rows}",
         "-frames:v", "1", str(out)], check=True)
    print(f"{cue_id}: {start:.1f}s to {end:.1f}s every {step}s -> {out}")


def synthesise(demo: Demo, backend: str) -> None:
    """One wav per cue, through video_transfer, each one listened back.

    A voice that drops an acronym leaves a sentence that still scans, so the
    only way to know is to hear it back and look for the identifier. Three
    attempts, the best kept.
    """
    directory = narration_dir(demo)
    directory.mkdir(parents=True, exist_ok=True)
    spec = directory / "lines.json"
    # `say` is what the voice is given; `check` is the written form the
    # listen-back looks for. They differ wherever a name had to be respelled to
    # be read correctly, and checking the spoken form would then verify the
    # workaround instead of the name.
    spec.write_text(json.dumps(
        [{"key": c.id, "say": c.spoken, "check": c.text} for c in demo.cues],
        ensure_ascii=False))

    runner = (
        "import json, re, shutil, sys\n"
        "from pathlib import Path\n"
        "from video_pipeline import dubscript\n"
        "from video_pipeline.tts import get_tts_backend\n"
        "from video_pipeline.transcribe import transcribe\n"
        "spec, out, voice, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]\n"
        # Only the acronyms are checked. Whisper writes thirty as 30 and
        # spells to its own taste; a word-for-word check would spend the
        # retries on spelling while an eaten NIST went through.
        "TOKEN = r'\\b[A-Z][A-Za-z0-9]*[A-Z0-9]\\b'\n"
        "NAMES = json.loads(sys.argv[5])\n"
        # One character of slack. Whisper spells what it hears -- NIST comes
        # back as NISD, which is the same sound -- and an exact match would
        # spend the retries on its spelling while a name that really was eaten
        # (ChromaDB as "Chromity B", four characters out) went through.
        "def near(token, flat):\n"
        "    n = len(token)\n"
        "    for i in range(len(flat) - n + 2):\n"
        "        for window in (flat[i:i+n], flat[i:i+n-1], flat[i:i+n+1]):\n"
        "            if sum(1 for a, b in zip(token, window) if a != b) + abs(n - len(window)) <= 1:\n"
        "                return True\n"
        "    return False\n"
        "def missing_of(sent, heard):\n"
        "    flat = re.sub(r'[^a-z0-9]', '', heard.lower())\n"
        "    wanted = set(re.findall(TOKEN, sent)) | {n for n in NAMES if n in sent}\n"
        "    return sorted(t for t in wanted if not near(re.sub(r'[^a-z0-9]', '', t.lower()), flat))\n"
        "b = get_tts_backend(name, language='en')\n"
        "prior = json.loads((out/'heard.json').read_text()) if (out/'heard.json').exists() else {}\n"
        "heard = {}\n"
        "for line in json.loads(spec.read_text()):\n"
        "    key, text, check = line['key'], dubscript.to_dub_text(line['say']), line['check']\n"
        "    wav, old = out/(key+'.wav'), prior.get(key)\n"
        # Re-judge the cached take rather than trusting the verdict stored
        # with it: the check itself changes, and a stale `missing` list is a
        # failure reported long after it stopped being true.
        "    if wav.exists() and old and old.get('sent') == text:\n"
        "        again = missing_of(check, old['heard'])\n"
        "        if not again:\n"
        "            old['missing'] = again; heard[key] = old; print('kept', key); continue\n"
        "    best = None\n"
        "    for attempt in range(1, 4):\n"
        "        take = out/(key+'.take.wav')\n"
        "        b.synthesize(text, take, speaker=voice)\n"
        "        h = ' '.join(s.text for s in transcribe(take, language='en').segments)\n"
        "        entry = {'backend': b.name, 'sent': text, 'check': check, 'heard': h,\n"
        "                 'missing': missing_of(check, h), 'attempts': attempt}\n"
        "        if best is None or len(entry['missing']) < len(best['missing']):\n"
        "            best = entry; shutil.copy(take, wav)\n"
        "        if not entry['missing']: break\n"
        "    take.unlink(missing_ok=True); heard[key] = best; print('made', key, best['missing'])\n"
        "(out/'heard.json').write_text(json.dumps(heard, ensure_ascii=False, indent=1))\n"
    )
    command = (f"source env.sh local >/dev/null && uv run --project . python -c "
               f"{shlex.quote(runner)} {shlex.quote(str(spec))} {shlex.quote(str(directory))} "
               f"{KOKORO_VOICE} {backend} {shlex.quote(json.dumps(list(IDENTIFIERS)))}")
    done = subprocess.run(["bash", "-c", command], cwd=VIDEO_TRANSFER, text=True)
    if done.returncode:
        sys.exit(f"video_transfer's TTS failed ({backend})")

    heard = json.loads((directory / "heard.json").read_text())
    bad = {k: v for k, v in heard.items() if v["missing"]}
    for key, entry in bad.items():
        print(f"warning: {key}: not heard back: {', '.join(entry['missing'])}\n"
              f"  sent:  {entry['sent']}\n  heard: {entry['heard']}", file=sys.stderr)
    print(f"\ndemo {demo.key}: {len(heard)} lines, {len(bad)} with a missing identifier")
    if bad:
        print("fix by giving those cues a `say` in scripts/demo_script.py, then re-run",
              file=sys.stderr)


def build(demo: Demo) -> None:
    durations = measured(demo)
    if durations is None:
        sys.exit(f"demo {demo.key}: no narration yet -- run --tts first")

    source_length = duration_of(demo.source)
    width, height = dimensions_of(demo.source)
    out_h = round(height * OUT_W / width / 2) * 2
    max_lines = max(len(wrap(c.text)) for c in demo.cues)
    band = band_height(out_h, max_lines)

    segs = segments(demo, durations, source_length)
    to_out, out_length = remapper(segs)

    srt_lines, starts = [], []
    for index, cue in enumerate(demo.cues, 1):
        start = to_out(cue.at)
        starts.append(start)
        end = min(to_out(cue.until) + 0.4, start + durations[cue.id] + 0.8)
        end = max(end, start + durations[cue.id])
        srt_lines.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n"
                         + "\n".join(wrap(cue.text)) + "\n")

    OUT.mkdir(parents=True, exist_ok=True)
    srt = OUT / f"{demo.out_stem}.en.srt"
    srt.write_text("\n".join(srt_lines))

    count = len(segs)
    graph = ["[0:v]split=" + str(count) + "".join(f"[i{k}]" for k in range(count))]
    for k, (start, end, factor) in enumerate(segs):
        graph.append(f"[i{k}]trim=start={start:.3f}:end={end:.3f},"
                     f"setpts=(PTS-STARTPTS)/{factor:.4f}[c{k}]")
    graph.append("".join(f"[c{k}]" for k in range(count))
                 + f"concat=n={count}:v=1:a=0,scale={OUT_W}:{out_h}:flags=lanczos,fps={FPS}[vc]")

    escaped = str(srt).replace(":", "\\:")
    # libass lays out against a 288-line script, so FontSize 13 lands near 40 px
    # on a 900 px frame: two lines and a margin inside the band.
    graph.append(
        f"[vc]pad={OUT_W}:{out_h + band}:0:0:color=0x0b0d12,"
        f"subtitles='{escaped}':force_style='FontName=Helvetica Neue,"
        f"FontSize={ASS_FONT_SIZE},"
        f"Alignment=2,MarginV={BAND_MARGIN},BorderStyle=1,Outline=1,Shadow=0,"
        f"PrimaryColour=&H00F2F2F2,OutlineColour=&H00000000'[v]")

    inputs, delays = [], []
    for index, (cue, start) in enumerate(zip(demo.cues, starts)):
        inputs += ["-i", str(narration_dir(demo) / f"{cue.id}.wav")]
        delays.append(f"[{index+1}:a]adelay={int(start*1000)}|{int(start*1000)}[a{index}]")
    mix = ("".join(f"[a{i}]" for i in range(len(demo.cues)))
           + f"amix=inputs={len(demo.cues)}:normalize=0[m];[m]apad[narr]")

    final = OUT / f"{demo.out_stem}.mp4"
    command = [FFMPEG, "-y", "-loglevel", "error", "-i", str(demo.source), *inputs,
               "-filter_complex", ";".join(delays) + ";" + mix + ";" + ";".join(graph),
               "-map", "[v]", "-map", "[narr]",
               "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
               "-crf", "26", "-preset", "slow", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "96k", "-shortest", str(final)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        sys.exit("ffmpeg failed:\n" + done.stderr[-3000:])

    size = final.stat().st_size / 1e6
    print(f"demo {demo.key}: {final}  {size:.1f} MB  {duration_of(final):.1f}s  "
          f"{'x'.join(map(str, dimensions_of(final)))}  audio={has_audio(final)}  "
          f"band {band}px for {max_lines} lines")
    print(f"  subtitles: {srt}")
    if size > 10:
        print(f"  warning: {size:.1f} MB is over GitHub's 10 MB attachment ceiling",
              file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", choices=sorted(DEMOS) + ["all"], default="all")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--frames", metavar="CUE",
                        help="tile the frames around a cue to check its timing")
    parser.add_argument("--before", type=float, default=2.0)
    parser.add_argument("--after", type=float, default=2.0)
    parser.add_argument("--step", type=float, default=1.0)
    parser.add_argument("--tts", action="store_true")
    parser.add_argument("--backend", default="kokoro", choices=("kokoro", "qwen3tts", "say"))
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()

    if args.frames:
        require_ffmpeg()
        frames(args.frames, args.before, args.after, args.step)
        return 0

    chosen = list(DEMOS.values()) if args.demo == "all" else [DEMOS[args.demo]]

    if args.check or not (args.tts or args.build):
        problems = sum(check(demo) for demo in chosen)
        print()
        return 1 if problems else 0

    require_ffmpeg()
    if args.tts:
        for demo in chosen:
            synthesise(demo, args.backend)
    if args.build:
        for demo in chosen:
            build(demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
