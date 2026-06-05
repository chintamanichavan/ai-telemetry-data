"""
Tests for apply_pit() — the PIT revision logic in ingesters/epoch.py.

This is the load-bearing function for the whole methodology: it decides when
a value becomes a revision (close prior row + append new) vs a no-op vs an
insert. Regressions here silently corrupt historical data.

Runs standalone (stdlib only):
    python tests/test_pit.py
Or with pytest:
    pytest tests/
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingesters.epoch import apply_pit

T0 = "2026-05-25T17:00:00Z"
T1 = "2026-05-25T18:00:00Z"
T2 = "2026-05-26T10:00:00Z"


def row(entity_id, name, *, observed_at=T0, valid_from=T0, valid_to="", **extra):
    return {
        "entity_id": entity_id,
        "name": name,
        "observed_at": observed_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        **extra,
    }


def test_insert_into_empty():
    out, ins, rev = apply_pit(
        [], [{"entity_id": "a", "name": "alpha"}], "entity_id", ["name"], T1
    )
    assert (ins, rev) == (1, 0)
    assert len(out) == 1
    r = out[0]
    assert r["entity_id"] == "a"
    assert r["name"] == "alpha"
    assert r["observed_at"] == T1
    assert r["valid_from"] == T1
    assert r["valid_to"] == ""


def test_unchanged_is_noop_no_churn():
    existing = [row("a", "alpha")]
    out, ins, rev = apply_pit(
        existing, [{"entity_id": "a", "name": "alpha"}], "entity_id", ["name"], T1
    )
    assert (ins, rev) == (0, 0)
    assert len(out) == 1
    assert out[0]["observed_at"] == T0  # original timestamp preserved


def test_revision_closes_prior_and_appends_new():
    existing = [row("a", "alpha")]
    out, ins, rev = apply_pit(
        existing, [{"entity_id": "a", "name": "beta"}], "entity_id", ["name"], T1
    )
    assert (ins, rev) == (0, 1)
    assert len(out) == 2

    closed = [r for r in out if r["valid_to"]]
    current = [r for r in out if not r["valid_to"]]
    assert len(closed) == 1 and len(current) == 1
    assert closed[0]["name"] == "alpha" and closed[0]["valid_to"] == T1
    assert current[0]["name"] == "beta"
    assert current[0]["valid_from"] == T1
    assert current[0]["observed_at"] == T1


def test_insert_alongside_existing_entity():
    existing = [row("a", "alpha")]
    out, ins, rev = apply_pit(
        existing, [{"entity_id": "b", "name": "beta"}], "entity_id", ["name"], T1
    )
    assert (ins, rev) == (1, 0)
    a = next(r for r in out if r["entity_id"] == "a")
    assert a["observed_at"] == T0  # untouched
    assert a["valid_to"] == ""


def test_untracked_field_change_is_noop():
    existing = [row("a", "alpha", source_url="old.example")]
    incoming = [{"entity_id": "a", "name": "alpha", "source_url": "new.example"}]
    out, ins, rev = apply_pit(existing, incoming, "entity_id", ["name"], T1)
    assert (ins, rev) == (0, 0)


def test_preserves_already_closed_history():
    """Pre-existing closed rows must not be mutated by a later revision."""
    existing = [
        row("a", "v1", observed_at=T0, valid_from=T0, valid_to=T1),
        row("a", "v2", observed_at=T1, valid_from=T1, valid_to=""),
    ]
    out, ins, rev = apply_pit(
        existing, [{"entity_id": "a", "name": "v3"}], "entity_id", ["name"], T2
    )
    assert (ins, rev) == (0, 1)
    assert len(out) == 3

    v1 = next(r for r in out if r["name"] == "v1")
    v2 = next(r for r in out if r["name"] == "v2")
    v3 = next(r for r in out if r["name"] == "v3")

    assert v1["valid_to"] == T1  # untouched closed row
    assert v2["valid_to"] == T2  # newly closed by this revision
    assert v3["valid_to"] == "" and v3["valid_from"] == T2


def test_only_changes_in_tracked_fields_trigger_revision():
    existing = [row("a", "alpha", tier="notable")]
    incoming = [{"entity_id": "a", "name": "alpha", "tier": "frontier"}]
    out, ins, rev = apply_pit(
        existing, incoming, "entity_id", ["name", "tier"], T1
    )
    assert (ins, rev) == (0, 1)


def test_empty_string_and_missing_key_compare_equal():
    """`.get(f, '') or ''` should make missing-key and '' indistinguishable."""
    existing = [row("a", "alpha", modalities="")]
    incoming = [{"entity_id": "a", "name": "alpha"}]  # no `modalities` key
    out, ins, rev = apply_pit(
        existing, incoming, "entity_id", ["name", "modalities"], T1
    )
    assert (ins, rev) == (0, 0)


def test_idempotent_second_call_with_same_data():
    """The ingester contract: re-running with unchanged upstream is a no-op."""
    incoming = [{"entity_id": "a", "name": "alpha"}]
    out1, ins1, rev1 = apply_pit([], incoming, "entity_id", ["name"], T1)
    out2, ins2, rev2 = apply_pit(out1, incoming, "entity_id", ["name"], T2)
    assert (ins1, rev1) == (1, 0)
    assert (ins2, rev2) == (0, 0)
    assert out1 == out2  # no mutation on second call


def test_resurrection_treated_as_insert():
    """If an entity's only row is already closed, incoming creates a NEW current.

    Semantics: entity dropped from upstream, came back. Historical row stays
    closed at the original timestamp; the return is a fresh insert, not a
    revision of the dead row.
    """
    existing = [row("a", "alpha", observed_at=T0, valid_from=T0, valid_to=T1)]
    out, ins, rev = apply_pit(
        existing, [{"entity_id": "a", "name": "alpha"}], "entity_id", ["name"], T2
    )
    assert (ins, rev) == (1, 0)
    assert len(out) == 2
    closed = [r for r in out if r["valid_to"]][0]
    current = [r for r in out if not r["valid_to"]][0]
    assert closed["valid_to"] == T1  # original closure preserved
    assert current["valid_from"] == T2


def test_multiple_incoming_same_entity_first_wins_then_revises():
    """Two incoming records for the same entity_id in one call.

    The ingester dedups before calling apply_pit, but the function should
    handle it deterministically: first insert, second revision.
    """
    incoming = [
        {"entity_id": "a", "name": "alpha"},
        {"entity_id": "a", "name": "beta"},
    ]
    out, ins, rev = apply_pit([], incoming, "entity_id", ["name"], T1)
    assert (ins, rev) == (1, 1)
    # Both rows have valid_from=T1; the alpha row has valid_to=T1 (zero-duration).
    assert len(out) == 2
    closed = [r for r in out if r["valid_to"]][0]
    current = [r for r in out if not r["valid_to"]][0]
    assert closed["name"] == "alpha" and closed["valid_to"] == T1
    assert current["name"] == "beta"


if __name__ == "__main__":
    tests = sorted(
        (n, f) for n, f in globals().items()
        if n.startswith("test_") and callable(f)
    )
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    total = len(tests)
    print(f"\n{total - failed}/{total} passed")
    sys.exit(1 if failed else 0)
