import unittest

from songli import agent, db, mock, rules


class TestParse(unittest.TestCase):
    def test_full(self):
        b = rules.parse("送长辈,生日,预算 500,对方喜欢喝茶")
        self.assertEqual(b["relation"], "长辈")
        self.assertEqual(b["occasion"], "生日")
        self.assertEqual(b["budget"], 500)
        self.assertIn("茶", b["interests"])

    def test_range_budget(self):
        self.assertEqual(rules.parse("同事 结婚 大概 300-800 元")["budget"], 800)

    def test_no_budget(self):
        self.assertIsNone(rules.parse("送朋友 乔迁")["budget"])

    def test_allergy(self):
        self.assertIn("过敏", rules.parse("朋友生日,对方香水过敏")["allergies"])


class TestMoney(unittest.TestCase):
    def test_split_total(self):
        s = rules.split_budget(500)
        self.assertEqual(s["total"], 500)
        self.assertEqual(s["main"], 400)
        self.assertEqual(s["flower"], 60)

    def test_split_small(self):
        s = rules.split_budget(100)
        self.assertEqual(s["main"] + s["flower"] + s["card"] + s["wrap"], 100)

    def test_split_none(self):
        self.assertIsNone(rules.split_budget(None)["main"])


class TestPool(unittest.TestCase):
    def test_pool_200(self):
        self.assertEqual(len(rules.gifts()), 200)

    def test_budget_filter(self):
        rows = rules.pool("同事", "生日", 100)
        self.assertTrue(all(g["low"] <= 100 for g in rows))
        self.assertTrue(rows)

    def test_relation_filter(self):
        rows = rules.pool("领导", None, None)
        self.assertTrue(all("领导" in g["relations"] for g in rows))

    def test_taboo_excluded(self):
        rows = rules.pool(None, None, None)
        self.assertFalse(any("香水" in g["name"] for g in rows))
        self.assertFalse(any(rules.gift_taboo(g) for g in rows))

    def test_sent_excluded(self):
        name = rules.gifts()[0]["name"]
        rows = rules.pool(None, None, None, sent=[name])
        self.assertNotIn(name, [g["name"] for g in rows])


class TestTaboo(unittest.TestCase):
    def test_rules_count(self):
        self.assertGreaterEqual(len(rules.taboo_rules()), 30)

    def test_clock(self):
        hits = rules.taboo_hits("想送个钟")
        self.assertTrue(any(h["id"] == "clock" for h in hits))

    def test_alcohol(self):
        self.assertTrue(any(h["id"] == "alcohol" for h in rules.taboo_hits("对方不喝酒")))

    def test_none(self):
        self.assertEqual(rules.taboo_hits("送朋友一本书"), [])


class TestSchemes(unittest.TestCase):
    def test_three(self):
        b = rules.parse("送长辈,生日,预算 500,喜欢喝茶")
        picked = rules.schemes(b)
        self.assertEqual(len(picked), 3)

    def test_categories_diverse(self):
        b = rules.parse("送朋友,生日,预算 300")
        picked = rules.schemes(b)
        self.assertEqual(len({g["category"] for g in picked}), 3)

    def test_within_budget(self):
        b = rules.parse("送同事,乔迁,预算 200")
        picked = rules.schemes(b)
        self.assertTrue(all(g["low"] <= 200 for g in picked))

    def test_check_shape(self):
        r = rules.check(rules.parse("送客户,节日,预算 800,不抽烟"))
        for k in ("brief", "split", "taboos", "schemes", "timing", "scripts"):
            self.assertIn(k, r)

    def test_scripts_have_refusal(self):
        self.assertTrue(rules.scripts({"relation": "朋友"})["refuse"])


class TestAgent(unittest.TestCase):
    def test_offline_structure(self):
        r = agent.analyze("送长辈,生日,预算 500", force_mock=True)
        self.assertEqual(r["mode"], "offline")
        self.assertEqual(len(r["schemes"]), 3)
        self.assertTrue(r["scripts"]["say"])
        self.assertTrue(r["risks"])

    def test_strip_money(self):
        self.assertNotIn("500", agent.strip_money("预算 500 元就行"))

    def test_guard_rejects_unknown_gift(self):
        r = rules.check(rules.parse("送长辈,生日,预算 500"))
        self.assertIsNone(agent.guard_reason("不存在的东西", "好", r["schemes"]))

    def test_guard_rejects_price(self):
        r = rules.check(rules.parse("送长辈,生日,预算 500"))
        name = r["schemes"][0]["name"]
        self.assertIsNone(agent.guard_reason(name, "这款 999 元很值", r["schemes"]))

    def test_guard_accepts(self):
        r = rules.check(rules.parse("送长辈,生日,预算 500"))
        name = r["schemes"][0]["name"]
        self.assertIsNotNone(agent.guard_reason(name, "长辈用得上", r["schemes"]))

    def test_mock_same_keys(self):
        r = rules.check(rules.parse("送朋友,生日,预算 200"))
        self.assertEqual(set(mock.draft(r)), {"reasons", "scripts", "refuse", "risks"})


class TestDb(unittest.TestCase):
    def test_record_and_history(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "t.db")
        db.use(path)
        db.record("张三", "生日", "朋友", "书·入门", 60)
        rows = db.history("张三")
        self.assertEqual(rows[0]["name"], "书·入门")
        self.assertIn("书·入门", db.sent_names("张三"))
        db.use(None)


if __name__ == "__main__":
    unittest.main()
