from transcript_genie.parallel import split_plan


def test_split_plan_covers_duration_contiguously():
    plan = split_plan(100.0, 4)
    assert len(plan) == 4
    assert plan[0] == (0.0, 25.0)
    # chunks are contiguous and cover the whole duration
    for i in range(1, 4):
        prev_end = plan[i - 1][0] + plan[i - 1][1]
        assert abs(plan[i][0] - prev_end) < 1e-6
    last_end = plan[-1][0] + plan[-1][1]
    assert abs(last_end - 100.0) < 1e-6


def test_split_plan_single_job():
    assert split_plan(50.0, 1) == [(0.0, 50.0)]


def test_split_plan_clamps_jobs():
    assert split_plan(30.0, 0) == [(0.0, 30.0)]


def test_split_plan_uneven_last_chunk_absorbs_remainder():
    plan = split_plan(10.0, 3)
    assert len(plan) == 3
    assert abs(sum(length for _, length in plan) - 10.0) < 1e-6
