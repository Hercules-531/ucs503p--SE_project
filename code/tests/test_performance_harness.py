from scripts.measure_performance import percentile, valid_provenance


def test_nearest_rank_percentile_and_provenance():
    assert percentile([5, 1, 4, 3, 2], 0.95) == 5
    assert percentile([], 0.95) is None
    assert valid_provenance(
        {
            "meta": {"source": "source", "last_verified": "2026-01-01"},
            "data": [{"source": {"url": "https://example.org", "last_verified": "2026-01-01"}}],
        }
    )
    assert not valid_provenance({"meta": {"source": "source"}, "data": [{}]})
    assert not valid_provenance(
        {"meta": {"source": "source", "last_verified": "2026-01-01"}, "data": []}
    )
