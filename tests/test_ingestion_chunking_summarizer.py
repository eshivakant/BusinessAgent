from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.summarizer import ExtractiveSummarizer


def test_chunk_text_splits_with_overlap() -> None:
    chunks = chunk_text("abcdefghij", chunk_size=6, overlap=2)
    assert chunks == ["abcdef", "efghij"]


def test_chunk_text_validates_overlap() -> None:
    try:
        chunk_text("content", chunk_size=5, overlap=5)
    except ValueError as exc:
        assert "overlap must be smaller than chunk_size" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid overlap")


def test_extractive_summarizer_uses_first_sentences() -> None:
    summarizer = ExtractiveSummarizer(max_sentences=2)
    text = "First sentence. Second sentence. Third sentence."
    summary = summarizer.summarize(text)
    assert summary == "First sentence. Second sentence."


def test_extractive_summarizer_handles_empty_text() -> None:
    summarizer = ExtractiveSummarizer(max_sentences=2)
    assert summarizer.summarize("   ") == ""
