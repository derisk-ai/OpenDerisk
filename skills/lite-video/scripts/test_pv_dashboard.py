#!/usr/bin/env python3
import os
import socket
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_dashboard  # noqa: E402


class TestPortAndState(unittest.TestCase):
    def test_pick_port_returns_free_port_in_band(self):
        # 8620 多半空闲；只要返回值在区间且非 None
        port = pv_dashboard.pick_port("127.0.0.1", 8620)
        self.assertIsNotNone(port)
        self.assertGreaterEqual(port, 8620)
        self.assertLessEqual(port, 8639)

    def test_pick_port_avoids_occupied(self):
        # 在带内找一个当前空闲端口 p 并占住，pick_port(preferred=p) 应返回不同端口
        holder = None
        p = None
        for cand in range(8620, 8640):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", cand))
                s.listen(1)
                holder = s
                p = cand
                break
            except OSError:
                s.close()
        self.assertIsNotNone(p, "8620-8639 均被占用，无法测试避让")
        try:
            got = pv_dashboard.pick_port("127.0.0.1", p)
            self.assertIsNotNone(got)
            self.assertNotEqual(got, p)
            self.assertGreaterEqual(got, 8620)
            self.assertLessEqual(got, 8639)
        finally:
            holder.close()

    def test_pick_port_none_when_band_full(self):
        # 占满 8620–8639，应返回 None
        holds = []
        try:
            for p in range(8620, 8640):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", p))
                    s.listen(1)
                    holds.append(s)
                except OSError:
                    s.close()
            self.assertIsNone(pv_dashboard.pick_port("127.0.0.1", 8620))
        finally:
            for s in holds:
                s.close()

    def test_state_roundtrip_and_clear(self):
        d = tempfile.mkdtemp()
        st = {"pid": 12345, "port": 8620, "bind": "127.0.0.1"}
        self.assertIsNone(pv_dashboard.read_state(d))
        pv_dashboard.write_state(d, st)
        self.assertEqual(pv_dashboard.read_state(d), st)
        pv_dashboard.clear_state(d)
        self.assertIsNone(pv_dashboard.read_state(d))


class TestProbeAndUrl(unittest.TestCase):
    def _dummy_server(self, port):
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        import threading
        class H(BaseHTTPRequestHandler):
            def log_message(self, fmt, *a):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv

    def test_probe_alive_true(self):
        srv = self._dummy_server(8731)
        try:
            self.assertTrue(pv_dashboard.probe_alive("127.0.0.1", 8731, timeout=1.0))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_probe_alive_false_on_dead_port(self):
        self.assertFalse(pv_dashboard.probe_alive("127.0.0.1", 8798, timeout=0.5))

    def test_health_check_true(self):
        srv = self._dummy_server(8732)
        try:
            self.assertTrue(pv_dashboard.health_check("127.0.0.1", 8732, attempts=5, interval=0.05))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_health_check_false(self):
        self.assertFalse(pv_dashboard.health_check("127.0.0.1", 8799, attempts=3, interval=0.01))

    def test_extract_url_found(self):
        out = "some banner\nDASHBOARD_URL=http://127.0.0.1:8620/\nmore"
        self.assertEqual(pv_dashboard.extract_url(out), "http://127.0.0.1:8620/")

    def test_extract_url_missing(self):
        self.assertIsNone(pv_dashboard.extract_url("no url here"))


class TestCmdStart(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # 造一个空 production.db 让库检查通过（不真 init）
        open(os.path.join(self.dir, "production.db"), "w").close()

    def _ns(self, **kw):
        import argparse
        base = dict(dir=self.dir, port=8620, bind="127.0.0.1")
        base.update(kw)
        return argparse.Namespace(**base)

    def test_start_reuses_running(self):
        # 已有状态且探活成功 → 复用，打印 DASHBOARD_URL 行，return 0，不调 fork
        pv_dashboard.write_state(self.dir, {"pid": 1, "port": 8620, "bind": "127.0.0.1"})
        with unittest.mock.patch("pv_dashboard.probe_alive", return_value=True), \
             unittest.mock.patch("pv_dashboard._fork_and_serve") as fk:
            rc = pv_dashboard.cmd_start(self._ns())
        self.assertEqual(rc, 0)
        self.assertFalse(fk.called)

    def test_start_no_port_returns_2(self):
        with unittest.mock.patch("pv_dashboard.pick_port", return_value=None):
            rc = pv_dashboard.cmd_start(self._ns())
        self.assertEqual(rc, 2)

    def test_start_missing_db_returns_1(self):
        os.remove(os.path.join(self.dir, "production.db"))
        with unittest.mock.patch("pv_dashboard.pick_port", return_value=8620):
            rc = pv_dashboard.cmd_start(self._ns())
        self.assertEqual(rc, 1)


class TestCmdStopStatus(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _ns(self):
        import argparse
        return argparse.Namespace(dir=self.dir, port=8620, bind="127.0.0.1")

    def test_stop_no_state(self):
        rc = pv_dashboard.cmd_stop(self._ns())
        self.assertEqual(rc, 0)

    def test_stop_dead_pid_clears_state(self):
        pv_dashboard.write_state(self.dir, {"pid": 999999, "port": 8620, "bind": "127.0.0.1"})
        rc = pv_dashboard.cmd_stop(self._ns())
        self.assertEqual(rc, 0)
        self.assertIsNone(pv_dashboard.read_state(self.dir))

    def test_status_not_running(self):
        pv_dashboard.write_state(self.dir, {"pid": 1, "port": 8620, "bind": "127.0.0.1"})
        with unittest.mock.patch("pv_dashboard.probe_alive", return_value=False):
            rc = pv_dashboard.cmd_status(self._ns())
        self.assertEqual(rc, 1)
        self.assertIsNone(pv_dashboard.read_state(self.dir))  # 已清理

    def test_status_running(self):
        pv_dashboard.write_state(self.dir, {"pid": 1, "port": 8620, "bind": "127.0.0.1"})
        with unittest.mock.patch("pv_dashboard.probe_alive", return_value=True):
            rc = pv_dashboard.cmd_status(self._ns())
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
