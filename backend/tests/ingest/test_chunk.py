from app.ingest.chunk import CHUNK_CHARS, CHUNK_OVERLAP, chunk_pages

STEP = CHUNK_CHARS - CHUNK_OVERLAP


def digits(n: int) -> str:
    return "".join(f"{i:04d}" for i in range(n // 4 + 1))[:n]


def test_short_page_is_one_chunk():
    chunks = chunk_pages(["Short page text."])
    assert [(c.chunk_id, c.page, c.text) for c in chunks] == [("1-0", 1, "Short page text.")]


def test_long_page_windows_overlap():
    page = digits(2000)
    chunks = chunk_pages([page])
    assert [c.text for c in chunks] == [page[0:800], page[650:1450], page[1300:2000]]
    assert chunks[1].text.startswith(chunks[0].text[-CHUNK_OVERLAP:])


def test_chunks_never_cross_pages():
    pages = [digits(1700), digits(900)]
    for chunk in chunk_pages(pages):
        assert chunk.text in pages[chunk.page - 1]


def test_blank_page_yields_no_chunks():
    chunks = chunk_pages(["", "   \n  ", "real text"])
    assert [c.page for c in chunks] == [3]


def test_chunk_ids_unique():
    chunks = chunk_pages([digits(2000), digits(2000)])
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)) == 6
