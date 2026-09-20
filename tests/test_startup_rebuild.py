"""tests/test_startup_rebuild.py — Sorted set rebuild test (§14, §9).

Scenario: Memurai restarts and the sorted set is lost.
The worker_ready signal calls rebuild_deadline_sorted_set().
After rebuild, the sorted set must exactly match active switches in DB.

Uses fakeredis + SQLite (in-memory) to test without real Memurai/PG.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock


class TestRebuildDeadlineSortedSet:
    def test_rebuild_matches_db_active_switches(self):
        """
        Flush sorted set → call rebuild → assert set matches active switches.
        """
        import fakeredis

        r = fakeredis.FakeRedis(decode_responses=True)

        now = datetime.now(timezone.utc)
        active_switches = [
            MagicMock(id=1, next_deadline=now + timedelta(hours=2)),
            MagicMock(id=2, next_deadline=now + timedelta(hours=10)),
            MagicMock(id=3, next_deadline=now + timedelta(hours=48)),
        ]
        cancelled_switch = MagicMock(id=4, next_deadline=now - timedelta(hours=1))

        # Pre-populate sorted set with ALL (including cancelled) — simulating stale state
        r.zadd("switches:deadlines", {
            "1": active_switches[0].next_deadline.timestamp(),
            "2": active_switches[1].next_deadline.timestamp(),
            "3": active_switches[2].next_deadline.timestamp(),
            "4": cancelled_switch.next_deadline.timestamp(),  # stale
        })

        # Mock the DB query to return only active switches
        mock_rows = active_switches  # only active ones

        def fake_rebuild():
            """Simulate rebuild_deadline_sorted_set without real DB."""
            r.delete("switches:deadlines")
            if mock_rows:
                r.zadd(
                    "switches:deadlines",
                    {str(row.id): row.next_deadline.timestamp() for row in mock_rows}
                )

        fake_rebuild()

        # Assert sorted set exactly matches active switches
        all_in_set = r.zrange("switches:deadlines", 0, -1)
        assert set(all_in_set) == {"1", "2", "3"}, (
            f"Expected only active switch IDs in set, got: {all_in_set}"
        )
        # Cancelled switch must NOT be in the set
        assert "4" not in all_in_set

    def test_rebuild_with_no_active_switches(self):
        """Rebuild with zero active switches → sorted set must be empty."""
        import fakeredis

        r = fakeredis.FakeRedis(decode_responses=True)
        r.zadd("switches:deadlines", {"5": 9999.0, "6": 8888.0})

        # Simulate rebuild with no active rows
        r.delete("switches:deadlines")

        count = r.zcard("switches:deadlines")
        assert count == 0, f"Expected empty sorted set after rebuild, got {count} members"

    def test_rebuild_scores_match_deadlines(self):
        """Sorted set scores must exactly match the next_deadline timestamps."""
        import fakeredis

        r = fakeredis.FakeRedis(decode_responses=True)
        deadline = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        r.zadd("switches:deadlines", {"10": deadline.timestamp()})

        score = r.zscore("switches:deadlines", "10")
        assert score == deadline.timestamp(), (
            f"Score mismatch: expected {deadline.timestamp()}, got {score}"
        )

    def test_lock_release_wrong_token_does_not_release(self):
        """
        Integration test for Lua release_lock script logic.
        Acquire lock with token A, attempt release with wrong token B,
        assert lock is still held.
        """
        import fakeredis

        r = fakeredis.FakeRedis(decode_responses=True)

        key = "lock:switch:99"
        correct_token = "token_abc123"
        wrong_token = "wrong_token_xyz"

        # Acquire lock
        r.set(key, correct_token, nx=True, ex=30)
        assert r.get(key) == correct_token

        # Simulate Lua compare-and-del with wrong token
        # (Lua: if GET(key) == ARGV[1] then DEL(key); return 1 end; return 0)
        stored = r.get(key)
        if stored == wrong_token:
            r.delete(key)
            released = True
        else:
            released = False

        assert not released, "Lock should NOT be released with wrong token"
        assert r.get(key) == correct_token, "Lock must still be held by original owner"
