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
import tempfile
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

#: How long a subtitle lingers past the moment its cue describes, so a line
#: does not vanish on the syllable it ends on.
SUBTITLE_TAIL = 0.4

#: Clear frame between one subtitle leaving and the next arriving. Without it
#: the tail above walks straight into the following cue.
SUBTITLE_GAP = 0.05

SUBTITLE_COLUMNS = 58
"""Where the search for a line length starts -- not a fact about any video.

It was measured once, on demo 1, and then used for both. That was wrong, and
wrong in a way only one of the two videos showed. libass sizes the font against
the finished frame, so the two recordings -- 3164 and 2624 px wide, scaled to a
common width -- do not get the same font: demo 1 draws at 69.5 px a line and
demo 2 at 78.3, thirteen percent bigger. Fifty-eight characters fits 1920 px at
the first size and does not at the second, so libass re-wrapped demo 2's
subtitles into three lines inside a band built for two, and the text ran out of
the band and over the picture. It shipped that way.

`layout()` now measures each video's own limit by rendering text and looking at
the pixels, and this is only where it starts looking."""

#: Grey level above which a pixel in a rendered probe counts as text. The band
#: is 0x0b0d12 (grey 12) and the text 0xF2F2F2 (242), so anything in between
#: separates them; this sits well clear of the antialiased edges either way.
TEXT_THRESHOLD = 80


# --- small helpers ----------------------------------------------------------

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def duration_of(path: Path) -> float:
    """Length in seconds, or exit. Never zero.

    Zero is the dangerous answer here, not the error. `segments` reads these
    lengths to decide how far to slow each stretch, and a line reported as
    zero seconds long needs no room at all -- so a truncated or unreadable wav
    became a stretch that played at full speed with silence over it, which
    looks exactly like a line nobody wrote.
    """
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).stdout.strip()
    try:
        seconds = float(out)
    except ValueError:
        sys.exit(f"ffprobe could not read a duration from {path}")
    if seconds <= 0:
        sys.exit(f"{path} is {seconds}s long; it is not a usable recording")
    return seconds


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


def wrap(text: str, columns: int) -> list[str]:
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


def style(band_top_margin: int = BAND_MARGIN) -> str:
    """The one force_style string, so the probe renders what the build renders.

    A measurement taken with different styling than the final draw measures
    nothing. Every caller goes through here.
    """
    return (f"FontName=Helvetica Neue,FontSize={ASS_FONT_SIZE},"
            f"Alignment=2,MarginV={band_top_margin},BorderStyle=1,Outline=1,Shadow=0,"
            f"PrimaryColour=&H00F2F2F2,OutlineColour=&H00000000")


def draw(lines: list[str], frame_h: int) -> list[tuple[int, int]]:
    """Render `lines` as a subtitle on a blank frame; return the rows it lit.

    Returns one ``(top, bottom)`` pair per band of consecutive lit rows, so the
    length is how many lines libass actually drew and the extremes are how far
    the text reached. Both matter: the count catches a line that was re-wrapped
    behind our back, and the extremes catch text leaving the band.

    Uses ffmpeg rather than a font-metrics library on purpose. This script has
    no dependencies beyond the two binaries it already needs, and more to the
    point a metrics estimate is a model of libass while this is libass. The
    frame comes back as raw 8-bit grey, which the standard library can read.
    """
    with tempfile.TemporaryDirectory() as tmp:
        srt = Path(tmp) / "probe.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n" + "\n".join(lines) + "\n")
        escaped = str(srt).replace(":", "\\:")
        done = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c=0x0b0d12:s={OUT_W}x{frame_h}:d=0.1",
             "-vf", f"subtitles='{escaped}':force_style='{style()}'",
             "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
            capture_output=True)
        if done.returncode or len(done.stdout) < OUT_W * frame_h:
            sys.exit("probe render failed:\n" + done.stderr.decode()[-2000:])
        return lit_rows(done.stdout, OUT_W, frame_h, 0, frame_h)


def lit_rows(raw: bytes, width: int, height: int,
             y0: int, y1: int) -> list[tuple[int, int]]:
    """Runs of consecutive rows containing a pixel brighter than the band."""
    runs: list[tuple[int, int]] = []
    start = None
    for y in range(max(0, y0), min(height, y1)):
        row = raw[y * width:(y + 1) * width]
        if row and max(row) >= TEXT_THRESHOLD:
            if start is None:
                start = y
        elif start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, min(height, y1)))
    return runs


def layout(demo: Demo, picture_h: int) -> tuple[int, int, dict[str, list[str]]]:
    """Find the line length and band height this particular video needs.

    Circular three ways over: the font size follows the frame height, the frame
    height is the picture plus the band, the band follows the line count, and
    the line count follows the line length that the font size allows. Solved by
    narrowing the line length until libass stops adding lines of its own, then
    re-deriving the band from what it actually drew.

    Each round costs one ffmpeg invocation on the widest line, which is the one
    that wraps first. `verify()` checks all of them against the finished video.
    """
    columns = SUBTITLE_COLUMNS
    for _ in range(16):
        wrapped = {cue.id: wrap(cue.text, columns) for cue in demo.cues}
        band = band_height(picture_h, max(len(v) for v in wrapped.values()))
        widest = max((line for lines in wrapped.values() for line in lines), key=len)
        if len(draw([widest], picture_h + band)) <= 1:
            return columns, band, wrapped
        columns -= 2
    sys.exit(f"demo {demo.key}: no line length under {SUBTITLE_COLUMNS} renders "
             f"as one line; the font or the frame is not what this script assumes")


def timestamp(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int(seconds % 3600 // 60), seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


# --- the timeline -----------------------------------------------------------

def estimated(cue: Cue) -> float:
    return cue.words / WORDS_PER_SECOND


def narration_dir(demo: Demo) -> Path:
    return BUILD / demo.key / "narration"


def measured(demo: Demo) -> dict[str, float] | None:
    """Real length of each synthesised line, if `--tts` has run *on this script*.

    Checking the wavs exist is not enough. Editing a cue and rebuilding without
    re-synthesising left the old recording in place under the new subtitle: the
    words on screen were the new ones, the voice said the old ones, and every
    timestamp after the edited cue was computed from the wrong length. The
    listen-back log records what each take was made from, so it can be
    compared.
    """
    directory = narration_dir(demo)
    wavs = {c.id: directory / f"{c.id}.wav" for c in demo.cues}
    if not all(p.exists() for p in wavs.values()):
        return None

    log = directory / "heard.json"
    if not log.exists():
        sys.exit(f"demo {demo.key}: {log} is missing, so the recordings cannot "
                 f"be matched against the script -- re-run --tts")
    heard = json.loads(log.read_text())
    stale = [c.id for c in demo.cues
             if heard.get(c.id, {}).get("check") != c.text]
    if stale:
        sys.exit(f"demo {demo.key}: the script has changed since these lines "
                 f"were recorded: {', '.join(stale)}. Re-run --tts.")
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


def synthesise(demo: Demo, backend: str) -> int:
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
        # One character of slack, and only for tokens long enough to afford it.
        # Whisper spells what it hears -- NIST comes back as NISD, the same
        # sound -- and an exact match would spend the retries on its spelling
        # while a name that really was eaten (ChromaDB as "Chromity B", four
        # characters out) went through.
        #
        # Three-letter tokens get no slack at all, because one character is the
        # whole of them. With a flat budget, `MCP` matched the two letters of
        # "M.C." (two compared, one for the length difference, budget spent) and
        # so did `PDF` against "P.D." and `CSF` against "C.S." -- the exact
        # failure this check exists to catch, passing as heard. All three are in
        # the script.
        "def near(token, flat):\n"
        "    n = len(token)\n"
        "    budget = 1 if n >= 4 else 0\n"
        "    for i in range(len(flat) - n + 2):\n"
        "        for window in (flat[i:i+n], flat[i:i+n-1], flat[i:i+n+1]):\n"
        "            if not window: continue\n"
        "            if sum(1 for a, b in zip(token, window) if a != b) + abs(n - len(window)) <= budget:\n"
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
        #
        # The voice and the backend are part of the key. Keyed on the words
        # alone, `--backend qwen3tts` re-used every kokoro take and reported a
        # complete run in a voice it never called.
        "    same = old and old.get('sent') == text \\\n"
        "        and old.get('backend') == b.name and old.get('voice') == voice\n"
        "    if wav.exists() and same:\n"
        "        again = missing_of(check, old['heard'])\n"
        "        if not again:\n"
        "            old['missing'] = again; heard[key] = old; print('kept', key); continue\n"
        "    best = None\n"
        "    for attempt in range(1, 4):\n"
        "        take = out/(key+'.take.wav')\n"
        "        b.synthesize(text, take, speaker=voice)\n"
        "        h = ' '.join(s.text for s in transcribe(take, language='en').segments)\n"
        "        entry = {'backend': b.name, 'voice': voice, 'sent': text,\n"
        "                 'check': check, 'heard': h,\n"
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
    return len(bad)


def build(demo: Demo) -> None:
    durations = measured(demo)
    if durations is None:
        sys.exit(f"demo {demo.key}: no narration yet -- run --tts first")

    source_length = duration_of(demo.source)
    width, height = dimensions_of(demo.source)
    out_h = round(height * OUT_W / width / 2) * 2
    columns, band, wrapped = layout(demo, out_h)
    max_lines = max(len(v) for v in wrapped.values())

    segs = segments(demo, durations, source_length)
    to_out, out_length = remapper(segs)

    starts = [to_out(cue.at) for cue in demo.cues]
    ends = []
    for index, cue in enumerate(demo.cues):
        start = starts[index]
        end = min(to_out(cue.until) + SUBTITLE_TAIL,
                  start + durations[cue.id] + 0.8)
        end = max(end, start + durations[cue.id])
        # A cue may not still be on screen when the next one arrives. The tail
        # above is what put it there: it was added to every cue and clamped
        # against nothing, so four of demo 2's six subtitles overlapped their
        # successor by the full 0.40 s and the frame carried two of them at
        # once. Shipped that way.
        if index + 1 < len(starts):
            limit = starts[index + 1] - SUBTITLE_GAP
            if end > limit:
                # `segments` slows a stretch until its line just fits, so a
                # slowed cue's narration ends exactly where the next one starts
                # and the clear frame has to come out of the subtitle. Losing
                # the gap is the design; losing more than that means the line
                # genuinely does not fit and the script is what needs changing.
                shortfall = start + durations[cue.id] - limit
                if shortfall > SUBTITLE_GAP + 0.01:
                    print(f"  warning: {cue.id} is still speaking "
                          f"{shortfall:.2f}s after {demo.cues[index+1].id} starts "
                          f"-- shorten the line or move the cue", file=sys.stderr)
                end = max(limit, start + 0.4)
        ends.append(end)

    srt_lines = [
        f"{index}\n{timestamp(start)} --> {timestamp(end)}\n"
        + "\n".join(wrapped[cue.id]) + "\n"
        for index, (cue, start, end) in enumerate(zip(demo.cues, starts, ends), 1)
    ]

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
    graph.append(
        f"[vc]pad={OUT_W}:{out_h + band}:0:0:color=0x0b0d12,"
        f"subtitles='{escaped}':force_style='{style()}'[v]")

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
          f"band {band}px for {max_lines} lines at {columns} columns")
    print(f"  subtitles: {srt}")
    if size > 10:
        print(f"  warning: {size:.1f} MB is over GitHub's 10 MB attachment ceiling",
              file=sys.stderr)

    if verify(demo, final, out_h, band, wrapped, starts, ends):
        sys.exit(f"demo {demo.key}: the finished video does not render its own "
                 f"subtitles correctly -- see above. Not shipping it.")


def verify(demo: Demo, final: Path, picture_h: int, band: int,
           wrapped: dict[str, list[str]], starts: list[float],
           ends: list[float]) -> int:
    """Look at the finished video and count the subtitle lines it actually has.

    Everything before this point is a prediction. The band is sized from a
    prediction of how many lines each cue takes, and when that prediction was
    wrong the video went out with its subtitles stacked over the picture and
    nobody noticed for a day -- the encode succeeded, the file played, the
    subtitles were there, there were just too many of them. So the last step
    reads pixels out of the finished file.

    Two questions per cue, both answerable without knowing what the text says:
    how many bands of lit rows are in the subtitle strip, and do any of them
    touch its edge.
    """
    problems = 0
    for cue, start, end in zip(demo.cues, starts, ends):
        at = (start + end) / 2
        done = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{at:.3f}",
             "-i", str(final), "-frames:v", "1",
             "-vf", f"crop={OUT_W}:{band}:0:{picture_h}",
             "-pix_fmt", "gray", "-f", "rawvideo", "-"],
            capture_output=True)
        if done.returncode or len(done.stdout) < OUT_W * band:
            print(f"  verify: could not read {cue.id} at {at:.2f}s", file=sys.stderr)
            problems += 1
            continue

        runs = lit_rows(done.stdout, OUT_W, band, 0, band)
        expected = len(wrapped[cue.id])
        if len(runs) != expected:
            print(f"  verify: {cue.id} at {at:.2f}s renders {len(runs)} lines, "
                  f"expected {expected}", file=sys.stderr)
            problems += 1
        if runs and (runs[0][0] <= 1 or runs[-1][1] >= band - 1):
            print(f"  verify: {cue.id} at {at:.2f}s touches the edge of the band "
                  f"(rows {runs[0][0]}-{runs[-1][1]} of {band})", file=sys.stderr)
            problems += 1

    # Two cues on screen at once shows up as more lines than either has, but
    # only if their line counts differ; check the timings directly as well.
    for index in range(len(starts) - 1):
        if ends[index] > starts[index + 1]:
            print(f"  verify: {demo.cues[index].id} runs "
                  f"{ends[index] - starts[index+1]:.2f}s into "
                  f"{demo.cues[index+1].id}", file=sys.stderr)
            problems += 1

    print(f"  verify: {len(demo.cues)} cues, {problems} problem(s)")
    return problems


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
    parser.add_argument("--force", action="store_true",
                        help="build even though a line was not heard back intact")
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
    unheard = 0
    if args.tts:
        for demo in chosen:
            unheard += synthesise(demo, args.backend)
    # `--tts --build` used to publish whatever came out, because the listen-back
    # result was printed and then dropped on the floor. A dropped acronym in a
    # sentence that still scans is the failure this whole step exists to catch;
    # noticing it and shipping anyway is worse than not checking.
    if unheard and not args.force:
        sys.exit(f"{unheard} line(s) came back missing an identifier -- not "
                 f"building. Give those cues a `say` in scripts/demo_script.py, "
                 f"or pass --force if the transcription is the thing that is wrong.")
    if args.build:
        for demo in chosen:
            build(demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
