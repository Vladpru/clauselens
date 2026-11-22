from spikes.s3_pymupdf import pick_gold_span


def test_pick_gold_span_prefers_longest_not_first():
    assert pick_gold_span(["state.", "This Agreement shall be governed by the laws of the State of New York."]) == (
        "This Agreement shall be governed by the laws of the State of New York."
    )
