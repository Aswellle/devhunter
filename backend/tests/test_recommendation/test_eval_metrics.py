"""
tests/test_recommendation/test_eval_metrics.py
推荐评测指标单元测试——纯函数，无 DB、无 I/O
"""
import math

import pytest

from app.recommendation.eval_metrics import ndcg_at_k, precision_at_k, recall_at_k

RANKED = ["a", "b", "c", "d", "e"]
RELEVANT = {"a", "c", "x"}  # a、c 在排序里，x 不在


class TestPrecisionAtK:
    def test_basic(self):
        """@1 命中 1/1；@2 命中 1/2；@4 命中 2/4"""
        assert precision_at_k(RANKED, RELEVANT, 1) == 1.0
        assert precision_at_k(RANKED, RELEVANT, 2) == 0.5
        assert precision_at_k(RANKED, RELEVANT, 4) == 0.5

    def test_k_exceeds_ranked(self):
        """k 超出排序长度时按实际长度计"""
        assert precision_at_k(["a"], RELEVANT, 5) == 1.0

    def test_empty_relevant(self):
        assert precision_at_k(RANKED, set(), 3) == 0.0

    def test_invalid_k(self):
        with pytest.raises(ValueError):
            precision_at_k(RANKED, RELEVANT, 0)


class TestRecallAtK:
    def test_basic(self):
        """排序内共命中 2 个相关（a, c），x 永远召回不到"""
        assert recall_at_k(RANKED, RELEVANT, 1) == 1 / 3
        assert recall_at_k(RANKED, RELEVANT, 2) == 1 / 3
        assert recall_at_k(RANKED, RELEVANT, 5) == 2 / 3

    def test_empty_relevant(self):
        assert recall_at_k(RANKED, set(), 3) == 0.0


class TestNDCGAtK:
    def test_perfect_ranking(self):
        """相关条目全在且按理想顺序排列 → NDCG = 1"""
        assert ndcg_at_k(["a", "c", "b"], {"a", "c"}, 3) == 1.0

    def test_partial(self):
        """c 排第二：DCG = 1 + 1/log2(3)，IDCG = 1 + 1/log2(3) + 1/2... 按 k=3 理想含 x"""
        ranked = ["c", "b", "a"]
        # 实际 DCG = 1/log2(2) + 0 + 1/log2(4) = 1 + 0.5 = 1.5
        # 理想（k=3，3 个相关）= 1 + 1/log2(3) + 1/log2(4)
        ideal = 1 + 1 / math.log2(3) + 0.5
        assert abs(ndcg_at_k(ranked, RELEVANT, 3) - 1.5 / ideal) < 1e-9

    def test_no_relevant_in_ranked(self):
        assert ndcg_at_k(["z", "y"], RELEVANT, 2) == 0.0

    def test_empty_relevant(self):
        assert ndcg_at_k(RANKED, set(), 3) == 0.0
