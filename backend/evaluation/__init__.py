"""
Academic Evaluation Suite for RESIN
Computes:
- IR Metrics: MRR, NDCG@K, Hit@K
- Lexical Metrics: BLEU (1, 2, 4), ROUGE (1, 2, L)
- RAGAS Triad: Faithfulness, Context Precision, Context Recall
"""
from evaluation.metrics import (
    compute_mrr,
    compute_ndcg_at_k,
    compute_hit_at_k,
    compute_bleu,
    compute_rouge,
    evaluate_faithfulness,
    evaluate_context_precision,
    evaluate_context_recall,
)

__all__ = [
    "compute_mrr",
    "compute_ndcg_at_k",
    "compute_hit_at_k",
    "compute_bleu",
    "compute_rouge",
    "evaluate_faithfulness",
    "evaluate_context_precision",
    "evaluate_context_recall",
]
