# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from membrain.config import Config
from membrain.engine import Engine


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(root=Path(self.tmp.name))
        self.eng = Engine(self.cfg)

    def tearDown(self):
        self.eng.close()
        self.tmp.cleanup()

    def test_remember_and_recall(self):
        self.eng.remember("阿宁讨厌被叫机器人", kind="fact", importance=0.9, who="阿宁")
        self.eng.remember("今天天气不错", kind="episode", importance=0.2)
        items = self.eng.recall("机器人", 3)
        self.assertTrue(items)
        self.assertIn("机器人", items[0]["text"])

    def test_dedup(self):
        a = self.eng.remember("阿宁讨厌被叫机器人", kind="fact")
        b = self.eng.remember("阿宁讨厌被叫机器人", kind="fact")
        self.assertTrue(a["ok"] and b["ok"])
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["deduped"])

    def test_decay_moves_tier(self):
        self.eng.remember("很久以前的事", kind="episode", importance=0.3)
        changed = self.eng.tick(now=1e10)
        self.assertIsInstance(changed, dict)

    def test_scope_isolated(self):
        self.eng.remember("群里的事", scope="group:1")
        self.eng.remember("私聊的事", scope="private:2")
        got = [it["text"] for it in self.eng.recall("事", 5, scope="private:2")]
        self.assertIn("私聊的事", got)
        self.assertNotIn("群里的事", got)


if __name__ == "__main__":
    unittest.main()
