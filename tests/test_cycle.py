"""Unit tests for the pure channel cycle state-machine helpers.

These test the arithmetic that decides how many single-step "cycle" actions are
needed to reach a target mode, independent of Home Assistant or the network.

Run from the repo root with:   python -m pytest tests/ -q
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "connectmypool"),
)

from cycle import (  # noqa: E402
    FILTER_PUMP_CYCLE,
    SIMPLE_CHANNEL_CYCLE,
    CycleError,
    cycle_steps,
    next_in_cycle,
)

# Filter pump: Off(0) -> Auto(1) -> Medium(4) -> High(5) -> Off
# Simple:      Off(0) -> Auto(1) -> On(2) -> Off


@pytest.mark.parametrize(
    "current,desired,expected",
    [
        (0, 0, 0),  # no-op
        (1, 1, 0),  # no-op
        (0, 1, 1),  # Off -> Auto
        (1, 4, 1),  # Auto -> Medium
        (1, 5, 2),  # Auto -> High (the common multi-step case)
        (1, 0, 3),  # Auto -> Off (full wrap)
        (5, 0, 1),  # High -> Off
        (5, 1, 2),  # High -> Auto
        (4, 5, 1),  # Medium -> High
    ],
)
def test_filter_cycle_steps(current, desired, expected):
    assert cycle_steps(current, desired, FILTER_PUMP_CYCLE) == expected


@pytest.mark.parametrize(
    "current,desired,expected",
    [
        (0, 0, 0),  # no-op
        (0, 1, 1),  # Off -> Auto
        (0, 2, 2),  # Off -> On (the common turn-on case)
        (1, 2, 1),  # Auto -> On
        (2, 0, 1),  # On -> Off
        (2, 1, 2),  # On -> Auto
        (1, 0, 2),  # Auto -> Off
    ],
)
def test_simple_cycle_steps(current, desired, expected):
    assert cycle_steps(current, desired, SIMPLE_CHANNEL_CYCLE) == expected


def test_steps_never_exceed_cycle_length():
    for cyc in (FILTER_PUMP_CYCLE, SIMPLE_CHANNEL_CYCLE):
        for c in cyc:
            for d in cyc:
                assert 0 <= cycle_steps(c, d, cyc) < len(cyc)


@pytest.mark.parametrize(
    "current,expected",
    [(0, 1), (1, 4), (4, 5), (5, 0)],  # one step advances through the filter sequence
)
def test_filter_next_in_cycle(current, expected):
    assert next_in_cycle(current, FILTER_PUMP_CYCLE) == expected


@pytest.mark.parametrize("current,expected", [(0, 1), (1, 2), (2, 0)])
def test_simple_next_in_cycle(current, expected):
    assert next_in_cycle(current, SIMPLE_CHANNEL_CYCLE) == expected


def test_walking_the_full_sequence_one_step_at_a_time():
    # Simulate the integration's per-step loop: from each start, take the
    # computed number of steps, advancing one at a time, and confirm arrival.
    for cyc in (FILTER_PUMP_CYCLE, SIMPLE_CHANNEL_CYCLE):
        for start in cyc:
            for target in cyc:
                steps = cycle_steps(start, target, cyc)
                mode = start
                for _ in range(steps):
                    mode = next_in_cycle(mode, cyc)
                assert mode == target


def test_unknown_mode_raises():
    with pytest.raises(CycleError):
        cycle_steps(99, 0, FILTER_PUMP_CYCLE)
    with pytest.raises(CycleError):
        cycle_steps(0, 99, SIMPLE_CHANNEL_CYCLE)
    with pytest.raises(CycleError):
        next_in_cycle(3, SIMPLE_CHANNEL_CYCLE)  # 3 is not a simple-channel mode
