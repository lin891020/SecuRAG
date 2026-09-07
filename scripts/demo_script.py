"""What the demo videos say, and when.

The two README demos are screen recordings with no audio. This is the
narration written against them: one sentence per cue, each pinned to the
seconds of the *source* recording it describes.

Cue times are in source time, never output time. `narrate_demo.py` may stretch
a stretch of video to give a line room to finish, which moves everything after
it; every timestamp that reaches ffmpeg is remapped through that. Editing a
number here means "this is when it happens in the original file", which is the
only clock that does not move under you.

`say` exists because `video_pipeline.dubscript.to_dub_text()` leaves an English
script completely untouched -- the acronym table is only consulted for Chinese
voices. So NIST, OWASP, CSF and MCP are read however Kokoro feels like reading
them, and when it gets one wrong the fix goes here: the subtitle keeps the
written form, `say` carries the spoken one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Cue:
    """One sentence, and the seconds of the source recording it belongs to."""

    id: str
    at: float
    until: float
    text: str
    say: str | None = None

    @property
    def window(self) -> float:
        return self.until - self.at

    @property
    def spoken(self) -> str:
        """What goes to the voice."""
        return self.say or self.text

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class Demo:
    key: str
    source: Path
    """The original recording, not the copy re-encoded for upload. Building
    from the compressed copy would be a second generation of loss on screen
    text that is already small."""

    out_stem: str
    cues: tuple[Cue, ...]

    @property
    def cue_by_id(self) -> dict[str, Cue]:
        return {c.id: c for c in self.cues}


MOVIES = Path.home() / "Movies"

#: Names the voice has to get right. The acronym pattern alone misses the ones
#: that are not all-caps, and those are exactly the ones a voice mangles:
#: measured, `ChromaDB` came back as "Chromity B" and `Ollama` as "Alama",
#: while `NIST` and `OWASP` were fine.
IDENTIFIERS = (
    "SecuRAG", "ChromaDB", "Ollama", "Postgres", "NIST", "OWASP", "CSF",
    "PDF", "MCP",
)

#: Words per second the narration is planned against. Kokoro's `af_heart` at
#: default rate; `--check` uses it to predict, `--build` uses the measured
#: length of each synthesised wav instead.
WORDS_PER_SECOND = 2.6

DEMO_1 = Demo(
    key="1",
    source=MOVIES / "Securag_Demo_en.mp4",
    out_stem="securag-demo-1-rag",
    # Times read off the recording at 2-second intervals (`--frames`). The first
    # pass of this table was written from a 6-second sample and had the PDF
    # scene four seconds late, so two lines described a screen that had already
    # gone.
    cues=(
        Cue("d1.0", 0.5, 9.0,
            "SecuRAG answers questions about your own security documents. "
            "Everything runs on one machine — nothing leaves the network."),
        # Probed against Kokoro on 2026-09-08: `ChromaDB` comes back as
        # "Chromity B" and `Ollama` as "Alama". `Chroma D B` and `Oh-llama` are
        # heard as the real names. The subtitle keeps the written form.
        Cue("d1.1", 10.0, 17.5,
            "Settings shows what it is made of: Postgres, ChromaDB and Ollama, "
            "all local, and the retrieval parameters in the open.",
            say="Settings shows what it is made of: Postgres, Chroma D B and Oh-llama, "
                "all local, and the retrieval parameters in the open."),
        Cue("d1.2", 18.0, 24.0,
            "A new document goes in — the NIST Cybersecurity Framework."),
        Cue("d1.3", 24.0, 31.0,
            "It is chunked and embedded on upload, and the table says when it is "
            "ready to answer."),
        Cue("d1.4", 31.5, 36.0,
            "The knowledge base goes from 31 chunks to 129.",
            say="The knowledge base goes from thirty-one chunks to a hundred and twenty-nine."),
        Cue("d1.5", 43.0, 51.0,
            "A question runs through three visible stages, each with its own timer: "
            "the input is checked, the store is searched, the model writes."),
        Cue("d1.6", 51.5, 56.0,
            "The answer cites the document and the page it came from."),
        Cue("d1.7", 56.5, 63.5,
            "Opening a citation shows the same passage in the original PDF."),
        Cue("d1.8", 65.0, 81.0,
            "A follow-up keeps the thread: retrieval runs again over the same "
            "knowledge base, and the answer builds on the first rather than "
            "starting over."),
        Cue("d1.9", 82.5, 99.0,
            "A third question, on incident response, comes back with the specific "
            "subcategories the framework defines — each one cited to its page."),
        # What the recording actually shows: all three stages run, and the
        # answer streams. The input guardrail stops the pipeline dead when it
        # blocks (rag_pipeline.py yields `blocked: True` and returns), so this
        # injection passed it and the model declined on its own.
        Cue("d1.10", 100.0, 107.0,
            "A prompt injection attempt. It clears the input guardrail, and the "
            "model refuses it anyway."),
    ),
)

DEMO_2 = Demo(
    key="2",
    source=MOVIES / "claude_securag_en.mp4",
    out_stem="securag-demo-2-mcp",
    cues=(
        Cue("d2.0", 0.0, 2.5,
            "The same knowledge base, from Claude Desktop."),
        Cue("d2.1", 2.5, 6.5,
            "SecuRAG exposes itself as an MCP server, so any MCP client can use it. "
            "Here it is in the connector list."),
        Cue("d2.2", 7.5, 10.0,
            "One question, in plain language, addressed to the knowledge base."),
        Cue("d2.3", 10.0, 15.0,
            "Claude discovers the tools the server offers, then calls ask_securag "
            "with the question.",
            say="Claude discovers the tools the server offers, then calls ask securag "
                "with the question."),
        Cue("d2.4", 15.0, 19.0,
            "The answer comes back through the same local retrieval pipeline — "
            "no copy-pasting between windows."),
        Cue("d2.5", 19.0, 21.0,
            "One knowledge base, two front ends."),
    ),
)

DEMOS = {d.key: d for d in (DEMO_1, DEMO_2)}
