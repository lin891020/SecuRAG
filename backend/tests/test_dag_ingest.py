"""The auto-ingest logic the Airflow DAG runs.

Lives here rather than beside the DAG because this is where the test runner is;
`dags/` is mounted read-only into the backend container for exactly this. The
DAG module itself imports `airflow` and cannot be loaded here -- what is under
test is `dags/securag_ingest_lib.py`, which imports none.

The behaviour that matters is idempotency on retry. The task raises when any
single upload fails and Airflow retries it once, so a run that ingested nine
files and failed on the tenth came back and uploaded all ten again: the list it
was working from was written before any of them existed in the knowledge base.
Duplicated documents are duplicated chunks answering every later query, and
nothing downstream notices.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, "/dags")

from securag_ingest_lib import ingest, ingested_filenames, scan  # noqa: E402

BACKEND = "http://backend:8000/api"


def _listing(*filenames: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"documents": [{"filename": f} for f in filenames]}
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def watched(tmp_path):
    """A watch folder with three ingestible files and one to be ignored."""
    for name in ("a.pdf", "b.txt", "c.md", "skip.zip"):
        (tmp_path / name).write_bytes(b"content")
    return tmp_path


class TestScan:
    def test_lists_only_new_supported_files(self, watched):
        with patch("securag_ingest_lib.requests.get", return_value=_listing("b.txt")):
            found = scan(watched, BACKEND)

        assert sorted(Path(p).name for p in found) == ["a.pdf", "c.md"]

    def test_missing_watch_folder_is_not_an_error(self, tmp_path):
        with patch("securag_ingest_lib.requests.get") as get:
            assert scan(tmp_path / "nope", BACKEND) == []
        get.assert_not_called()


class TestIngestIdempotency:
    def test_a_retry_does_not_re_upload_what_already_landed(self, watched):
        """The bug this module was split out to test.

        First attempt: three files, the third upload fails, so the task raises
        and Airflow retries with the same list. By then the first two are in
        the knowledge base, and re-sending them would duplicate them.
        """
        files = [str(watched / n) for n in ("a.pdf", "b.txt", "c.md")]

        ok, boom = MagicMock(), MagicMock()
        boom.raise_for_status.side_effect = requests.RequestException("500")

        with (
            patch("securag_ingest_lib.requests.get", return_value=_listing()),
            patch("securag_ingest_lib.requests.post", side_effect=[ok, ok, boom]) as post,
        ):
            with pytest.raises(RuntimeError, match="c.md"):
                ingest(files, BACKEND)
        assert post.call_count == 3

        # the retry: two of them are in the knowledge base now
        with (
            patch("securag_ingest_lib.requests.get",
                  return_value=_listing("a.pdf", "b.txt")),
            patch("securag_ingest_lib.requests.post", return_value=ok) as post,
        ):
            assert ingest(files, BACKEND) == 1

        assert post.call_count == 1, "the retry re-uploaded files that were already in"
        sent = post.call_args.kwargs["files"]["file"][0]
        assert sent == "c.md"

    def test_nothing_is_uploaded_when_everything_already_landed(self, watched):
        files = [str(watched / n) for n in ("a.pdf", "b.txt")]
        with (
            patch("securag_ingest_lib.requests.get",
                  return_value=_listing("a.pdf", "b.txt")),
            patch("securag_ingest_lib.requests.post") as post,
        ):
            assert ingest(files, BACKEND) == 0
        post.assert_not_called()

    def test_it_stops_rather_than_guess_when_the_check_fails(self, watched):
        """Not knowing what is already in is a reason to stop, not to re-send."""
        with (
            patch("securag_ingest_lib.requests.get",
                  side_effect=requests.RequestException("connection refused")),
            patch("securag_ingest_lib.requests.post") as post,
        ):
            with pytest.raises(RuntimeError, match="Could not check"):
                ingest([str(watched / "a.pdf")], BACKEND)
        post.assert_not_called()

    def test_an_empty_list_does_not_call_the_backend(self):
        with patch("securag_ingest_lib.requests.get") as get:
            assert ingest([], BACKEND) == 0
            assert ingest(None, BACKEND) == 0
        get.assert_not_called()


def test_ingested_filenames_reads_the_document_list():
    with patch("securag_ingest_lib.requests.get", return_value=_listing("x.pdf", "y.md")):
        assert ingested_filenames(BACKEND) == {"x.pdf", "y.md"}
