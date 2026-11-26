"""集成测试:HTTP 层、CLI 端到端、四份真实需求跑出来的东西是否站得住。

单测只测函数,这里测「真发请求、真起进程、真读文件」之后用户看到的结果。
"""

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from songli import agent, llm, rules, web

ROOT = Path(__file__).resolve().parents[1]
CASES = ["case-01", "case-02", "case-03", "case-04"]


def case_text(cid):
    return (ROOT / "examples" / (cid + ".txt")).read_text(encoding="utf-8").strip()


def run_cli(*args, stdin=""):
    return subprocess.run([sys.executable, "-m", "songli", *args],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", input=stdin, timeout=60)


class TestHttp(unittest.TestCase):
    """真起一个 http.server,用 socket 发原始请求。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp, "s.db")
        cls.srv = ThreadingHTTPServer(
            ("127.0.0.1", 0), web._handler(llm.default_config(), True, cls.db_path))
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def conn(self):
        return socket.create_connection(("127.0.0.1", self.port), timeout=8)

    def read_response(self, sock):
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        head, body = buf.split(b"\r\n\r\n", 1)
        text = head.decode("latin-1")
        m = re.search(r"Content-Length: (\d+)", text)
        n = int(m.group(1)) if m else 0
        while len(body) < n:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
        return text.split("\r\n")[0], body[:n]

    def send(self, sock, path, body=None):
        if body is None:
            head = "GET %s HTTP/1.1\r\nHost: x\r\n\r\n" % path
        else:
            head = ("POST %s HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                    "Content-Length: %d\r\n\r\n%s" % (path, len(body), body.decode("utf-8")))
        sock.sendall(head.encode("utf-8"))
        return self.read_response(sock)

    def test_page_is_html(self):
        s = self.conn()
        status, body = self.send(s, "/")
        s.close()
        self.assertIn("200", status)
        self.assertIn("送礼".encode("utf-8"), body)

    def test_status_says_mock(self):
        s = self.conn()
        status, body = self.send(s, "/api/status")
        s.close()
        self.assertIn("200", status)
        self.assertTrue(json.loads(body)["mock"])

    def test_plan_returns_three_schemes_and_split(self):
        s = self.conn()
        status, body = self.send(s, "/api/plan",
                                 json.dumps({"text": case_text("case-01")}).encode("utf-8"))
        s.close()
        self.assertIn("200", status)
        r = json.loads(body)
        self.assertEqual(len(r["schemes"]), 3)
        self.assertEqual(r["split"]["total"], 500)
        self.assertEqual(r["split"]["main"] + r["split"]["flower"]
                         + r["split"]["card"] + r["split"]["wrap"], 500)

    def test_plan_writes_history(self):
        s = self.conn()
        self.send(s, "/api/plan",
                  json.dumps({"text": "送给同事,乔迁,预算 200", "save": True}).encode("utf-8"))
        s.close()
        s = self.conn()
        status, body = self.send(s, "/api/history")
        s.close()
        self.assertIn("200", status)
        self.assertTrue(json.loads(body))

    def test_truncated_json_is_400(self):
        # issue #3:截断的 body 原来回 500,还带 json 解析器原文
        s = self.conn()
        status, body = self.send(s, "/api/plan", '{"text": "送长辈,生日,预算 500'.encode("utf-8"))
        s.close()
        self.assertIn("400", status)
        self.assertIn("不是合法 JSON".encode("utf-8"), body)
        self.assertNotIn(b"Unterminated", body)
        self.assertNotIn(b"Expecting", body)

    def test_empty_body_is_not_500(self):
        s = self.conn()
        status, _ = self.send(s, "/api/plan", b"")
        s.close()
        self.assertIn("200", status)

    def test_unknown_path_is_404(self):
        s = self.conn()
        status, _ = self.send(s, "/api/nope", '{"text":"送朋友"}'.encode("utf-8"))
        s.close()
        self.assertIn("404", status)

    def test_get_unknown_is_404(self):
        s = self.conn()
        status, _ = self.send(s, "/nope")
        s.close()
        self.assertIn("404", status)


class TestRules(unittest.TestCase):
    """四条 issue 对应的行为就地钉住。"""

    def test_zh_budget_five_hundred(self):
        # issue #6:「预算五百」原来整块丢掉
        self.assertEqual(rules.parse("送领导,预算五百,爱喝茶")["budget"], 500)
        self.assertEqual(rules.parse("同事乔迁,预算八百左右")["budget"], 800)
        self.assertEqual(rules.parse("送朋友,预算一千二")["budget"], 1200)
        self.assertEqual(rules.zh_number("两百五"), 250)
        self.assertEqual(rules.zh_number("十五"), 15)

    def test_digit_budget_still_wins(self):
        self.assertEqual(rules.parse("送长辈,生日,预算 500")["budget"], 500)
        self.assertEqual(rules.parse("预算 500-800 元")["budget"], 800)

    def test_relation_synonyms(self):
        # issue #4:口语称呼判不出关系
        self.assertEqual(rules.parse("送外婆,生日,预算五百")["relation"], "长辈")
        self.assertEqual(rules.parse("给外甥女满月,预算 300")["relation"], "孩子")
        self.assertEqual(rules.parse("送爸妈,生日,预算 200")["relation"], "父母")
        self.assertEqual(rules.parse("送闺蜜,生日,预算 200")["relation"], "朋友")
        self.assertEqual(rules.parse("送老板,节日,预算 800")["relation"], "领导")

    def test_no_relation_risk_does_not_claim_unwritten(self):
        # issue #4 的另一半:判不出时说「没写关系类别」,不再断言「没写送给谁」
        from songli import mock
        base = rules.check(rules.parse("想送点东西,预算 200"), None, "")
        risks = mock.risks(base)
        self.assertTrue(any("关系类别" in x for x in risks))
        self.assertFalse(any("没写送给谁" in x for x in risks))

    def test_split_budget_never_negative(self):
        # issue #5:预算 50 时包装变成 -5
        for budget in (50, 60, 80, 100, 200, 300, 500, 800, 1000):
            s = rules.split_budget(budget)
            for key in ("main", "flower", "card", "wrap"):
                self.assertGreaterEqual(s[key], 0, "%s 出现负数: %r" % (budget, s))
            self.assertEqual(s["main"] + s["flower"] + s["card"] + s["wrap"], budget)

    def test_split_budget_big_numbers_unchanged(self):
        self.assertEqual(rules.split_budget(500),
                         {"main": 400, "flower": 60, "card": 20, "wrap": 20, "total": 500})
        self.assertEqual(rules.split_budget(800)["main"], 640)

    def test_month_occasion_falls_back_with_note(self):
        # issue #7:池里没有「满月」品类,原来输出空的三套方案
        brief = rules.parse(case_text("case-04"))
        base = rules.check(brief, None, case_text("case-04"))
        self.assertEqual(len(base["schemes"]), 3)
        self.assertIn("满月", base["note"] or "")

    def test_taboo_hits_and_gift_filter(self):
        self.assertTrue(any(t["name"] == "钟表" for t in rules.taboo_hits("想送个钟")))
        self.assertTrue(rules.gift_taboo({"name": "厨房刀具套装·入门"}))

    def test_reason_guard_and_strip(self):
        schemes = [{"name": "茶叶礼盒·高端"}]
        self.assertIsNone(agent.guard_reason("茶叶礼盒·高端", "这个 999 元很体面", schemes))
        self.assertIsNone(agent.guard_reason("不存在的东西", "体面", schemes))
        self.assertIn("该价位", agent.strip_money("预算 500 元刚好"))


class TestCases(unittest.TestCase):
    """四份真实需求各自该看到的那条结论。"""

    def test_case01_budget_and_relation(self):
        r = rules.check(rules.parse(case_text("case-01")), None, case_text("case-01"))
        self.assertEqual(r["brief"]["budget"], 500)
        self.assertEqual(r["brief"]["relation"], "长辈")
        self.assertEqual([t["name"] for t in r["taboos"]], ["酒类"])

    def test_case02_avoids_clock_and_knife(self):
        r = rules.check(rules.parse(case_text("case-02")), None, case_text("case-02"))
        names = [t["name"] for t in r["taboos"]]
        self.assertIn("钟表", names)
        self.assertIn("刀具", names)
        for g in r["schemes"]:
            self.assertNotIn("钟", g["name"])
            self.assertNotIn("刀", g["name"])

    def test_case03_split_matches_budget(self):
        r = rules.check(rules.parse(case_text("case-03")), None, case_text("case-03"))
        self.assertEqual(r["split"]["total"], 300)
        self.assertTrue(r["schemes"])

    def test_case04_has_schemes_and_note(self):
        r = rules.check(rules.parse(case_text("case-04")), None, case_text("case-04"))
        self.assertTrue(r["schemes"])
        self.assertIn("满月", r["note"])

    def test_every_case_produces_output_file(self):
        for cid in CASES:
            path = ROOT / "examples" / "out" / (cid + ".md")
            self.assertTrue(path.exists(), cid)
            self.assertGreater(path.stat().st_size, 300, cid)


class TestCli(unittest.TestCase):
    """真起进程跑 python -m songli。"""

    def test_plan_file_case01(self):
        r = run_cli("--mock", "plan", "--file", "examples/case-01.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("预算:500 元", r.stdout)
        self.assertIn("关系:长辈", r.stdout)
        self.assertIn("主礼 400 / 花 60 / 卡 20 / 包装 20", r.stdout)

    def test_plan_small_budget_no_negative(self):
        r = run_cli("--mock", "plan", "--text", "送朋友毕业,预算 50")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("-5", r.stdout)
        self.assertIn("包装 0", r.stdout)

    def test_plan_json(self):
        r = run_cli("--mock", "--json", "plan", "--text", "送同事,乔迁,预算 200")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["schemes"]), 3)
        self.assertEqual(data["split"]["total"], 200)

    def test_plan_without_text_exits_2(self):
        r = run_cli("--mock", "plan", stdin="")
        self.assertEqual(r.returncode, 2)
        self.assertIn("没有描述", r.stderr)

    def test_check_finds_taboo(self):
        r = run_cli("--mock", "check", "--text", "想送个钟给他")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("命中", r.stdout)
        self.assertIn("钟表", r.stdout)

    def test_pool_lists_gifts(self):
        r = run_cli("--mock", "pool", "--text", "送同事,乔迁,预算 200")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("可选礼物池", r.stdout)
        self.assertIn("·", r.stdout)

    def test_history_empty_db(self):
        tmp = tempfile.mkdtemp()
        r = run_cli("--mock", "--db", os.path.join(tmp, "h.db"), "history")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("还没有记录", r.stdout)

    def test_history_after_save(self):
        tmp = tempfile.mkdtemp()
        dbp = os.path.join(tmp, "h.db")
        r1 = run_cli("--mock", "--db", dbp, "plan", "--save", "--recipient", "外婆",
                     "--text", "送外婆,生日,预算 500")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = run_cli("--mock", "--db", dbp, "history", "--recipient", "外婆")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("外婆", r2.stdout)
        self.assertIn("生日", r2.stdout)
        self.assertIn("元", r2.stdout)

    def test_version_prints(self):
        r = run_cli("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("songli", r.stdout)


if __name__ == "__main__":
    unittest.main()
