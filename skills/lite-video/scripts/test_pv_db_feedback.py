#!/usr/bin/env python3
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_db  # noqa: E402


def make_proj():
    d = tempfile.mkdtemp()
    pv_db.init_project(d, "测试", None, 1080, 1920, "zh-CN-YunxiNeural", 30, "imageflow")
    return d


def open_conn(d):
    return pv_db.connect(d)


def add(d, conn, content, stage="", shot=None):
    return pv_db.add_feedback(conn, stage, shot, content)


class TestCheckAndMark(unittest.TestCase):
    def test_marks_pending_to_seen_idempotent(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "f1", "script"); add(d, conn, "f2", "tts", 3)
        with contextlib.redirect_stdout(io.StringIO()):
            rows = pv_db.check_and_mark_pending(conn)
        self.assertEqual(len(rows), 2)
        after = conn.execute("SELECT status,seen_at FROM feedback ORDER BY id").fetchall()
        self.assertEqual([r["status"] for r in after], ["seen", "seen"])
        self.assertTrue(all(r["seen_at"] for r in after))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pv_db.check_and_mark_pending(conn), [])
        conn.close()

    def test_columns_exist_on_fresh_db(self):
        d = make_proj(); conn = open_conn(d)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(feedback)")]
        for c in ("seen_at", "fix_reason", "fixed_at"):
            self.assertIn(c, cols)
        conn.close()


class TestFixListResolve(unittest.TestCase):
    def setUp(self):
        self.d = make_proj(); self.conn = open_conn(self.d)
        add(self.d, self.conn, "p1", "script"); add(self.d, self.conn, "p2", "tts")

    def tearDown(self):
        self.conn.close()

    def test_fix_seen_to_fixed_with_reason(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.list_feedback(self.conn, "pending")  # →seen
            pv_db.fix_feedback(self.conn, 1, "改了镜头1文案")
        r = self.conn.execute("SELECT status,fix_reason,fixed_at FROM feedback WHERE id=1").fetchone()
        self.assertEqual(r["status"], "fixed")
        self.assertEqual(r["fix_reason"], "改了镜头1文案")
        self.assertTrue(r["fixed_at"])

    def test_fix_accepts_pending_directly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.fix_feedback(self.conn, 1, "直接修")  # pending→fixed
        self.assertEqual(self.conn.execute(
            "SELECT status FROM feedback WHERE id=1").fetchone()["status"], "fixed")

    def test_resolve_fixed_to_resolved(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.list_feedback(self.conn, "pending"); pv_db.fix_feedback(self.conn, 1, "r")
            pv_db.resolve_feedback(self.conn, 1)
        self.assertEqual(self.conn.execute(
            "SELECT status FROM feedback WHERE id=1").fetchone()["status"], "resolved")

    def test_resolve_pending_fallback(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.resolve_feedback(self.conn, 1)  # pending→resolved 保底
        self.assertEqual(self.conn.execute(
            "SELECT status FROM feedback WHERE id=1").fetchone()["status"], "resolved")

    def test_unresolved_includes_fixed(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.list_feedback(self.conn, "pending"); pv_db.fix_feedback(self.conn, 1, "r")
            pv_db.resolve_feedback(self.conn, 2)   # id2→resolved
        rows = self.conn.execute(
            "SELECT * FROM feedback WHERE status!='resolved' ORDER BY id").fetchall()
        self.assertEqual([r["id"] for r in rows], [1])

    def test_seen_list_readonly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.list_feedback(self.conn, "pending")  # →seen
            pv_db.list_feedback(self.conn, "seen")
        self.assertEqual([r["status"] for r in self.conn.execute(
            "SELECT status FROM feedback ORDER BY id")], ["seen", "seen"])


class TestWeldAndCounts(unittest.TestCase):
    def test_start_stage_marks_pending_nonblocking(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "fb", "script")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.start_stage(conn, "script")
        self.assertEqual(conn.execute("SELECT status FROM feedback WHERE id=1").fetchone()["status"], "seen")
        self.assertEqual(conn.execute("SELECT status FROM stages WHERE name='script'").fetchone()["status"], "in_progress")
        conn.close()

    def test_gate_stage_marks_pending(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "fb", "script")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.gate_stage(conn, "script", "摘要")
        self.assertEqual(conn.execute("SELECT status FROM feedback WHERE id=1").fetchone()["status"], "seen")
        self.assertEqual(conn.execute("SELECT status FROM stages WHERE name='script'").fetchone()["status"], "awaiting_human")
        conn.close()

    def test_start_stage_not_blocked_by_fixed_unresolved(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "fb", "script")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.check_and_mark_pending(conn); pv_db.fix_feedback(conn, 1, "修了")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.start_stage(conn, "script")  # 不应因 fixed 未 resolved 而 raise
        self.assertEqual(conn.execute("SELECT status FROM stages WHERE name='script'").fetchone()["status"], "in_progress")
        conn.close()

    def test_next_stage_warns_unfixed_only(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "a", "script"); add(d, conn, "b", "tts"); add(d, conn, "c", "plan")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.check_and_mark_pending(conn)      # 3→seen
            pv_db.fix_feedback(conn, 1, "r")        # id1→fixed
            pv_db.resolve_feedback(conn, 2)         # id2→resolved
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pv_db.next_stage(conn)
        self.assertIn("未修复反馈 1 条", buf.getvalue())

    def test_status_report_warns_unfixed(self):
        d = make_proj(); conn = open_conn(d)
        add(d, conn, "a", "script")
        with contextlib.redirect_stdout(io.StringIO()):
            pv_db.check_and_mark_pending(conn)      # →seen(未修复)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pv_db.status_report(conn)
        self.assertIn("未修复反馈 1 条", buf.getvalue())
        conn.close()


if __name__ == "__main__":
    unittest.main()
