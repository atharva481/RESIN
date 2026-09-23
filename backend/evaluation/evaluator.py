import csv
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional
import numpy as np

from evaluation.metrics import (
    compute_bleu,
    compute_hit_at_k,
    compute_mrr,
    compute_ndcg_at_k,
    compute_rouge,
    evaluate_context_precision,
    evaluate_context_recall,
    evaluate_faithfulness,
)

logger = logging.getLogger("evaluation")


class RAGEvaluator:
    """
    Automated Academic Benchmark Evaluator for the RESIN RAG Platform.
    Computes:
      - IR Metrics: MRR, NDCG@3, NDCG@5, Hit@3, Hit@5
      - Lexical Generation: BLEU-1, BLEU-2, BLEU-4, ROUGE-1, ROUGE-2, ROUGE-L
      - RAGAS Triad: Faithfulness, Context Precision, Context Recall
    """

    def __init__(
        self,
        retrieval_service: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        gemini_judge_client: Optional[Any] = None,
    ):
        self.retrieval_service = retrieval_service
        self.rag_service = rag_service
        self.gemini_judge = gemini_judge_client

    def evaluate_sample(
        self,
        sample: Dict[str, Any],
        top_k: int = 5,
        use_cached_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate a single benchmark sample question against a paper.
        """
        sample_id = sample.get("id", "sample")
        paper_id = sample.get("paper_id")
        query = sample.get("question")
        ground_truth_answer = sample.get("ground_truth_answer", "")
        keywords = [k.lower() for k in sample.get("relevant_keywords", [])]

        # 1. Retrieve Context Chunks
        retrieved_contexts: List[str] = []
        retrieved_ids: List[int] = []
        relevant_mask: List[int] = []

        if self.retrieval_service and paper_id and not use_cached_run:
            try:
                citations = self.retrieval_service.retrieve_context(
                    query=query,
                    paper_id=paper_id,
                    top_k=top_k,
                )
                for rank, c in enumerate(citations):
                    snippet = c.content_snippet or ""
                    retrieved_contexts.append(snippet)
                    chunk_idx = getattr(c, "chunk_index", rank)
                    retrieved_ids.append(chunk_idx)

                    # Assess relevance of chunk via keyword overlap
                    snip_lower = snippet.lower()
                    matched = any(kw in snip_lower for kw in keywords) if keywords else True
                    if matched:
                        relevant_mask.append(chunk_idx)
            except Exception as e:
                logger.error(f"Error retrieving for sample {sample_id}: {e}")

        # Fallback if no retrieval service or offline sample with pre-provided context
        if not retrieved_contexts and "retrieved_contexts" in sample:
            retrieved_contexts = sample["retrieved_contexts"]
            retrieved_ids = list(range(len(retrieved_contexts)))
            for idx, ctx in enumerate(retrieved_contexts):
                if any(kw in ctx.lower() for kw in keywords):
                    relevant_mask.append(idx)

        # 2. Compute Information Retrieval (IR) Metrics
        mrr = compute_mrr(retrieved_ids, relevant_mask)
        ndcg_3 = compute_ndcg_at_k(retrieved_ids, relevant_mask, k=3)
        ndcg_5 = compute_ndcg_at_k(retrieved_ids, relevant_mask, k=5)
        hit_3 = compute_hit_at_k(retrieved_ids, relevant_mask, k=3)
        hit_5 = compute_hit_at_k(retrieved_ids, relevant_mask, k=5)

        # 3. Generate Answer
        generated_answer = ""
        if self.rag_service and paper_id and not use_cached_run:
            try:
                resp = self.rag_service.answer_question(
                    paper_id=paper_id,
                    question=query,
                )
                generated_answer = resp.answer or ""
            except Exception as e:
                logger.error(f"Error generating answer for sample {sample_id}: {e}")
                generated_answer = ""
        elif "generated_answer" in sample:
            generated_answer = sample["generated_answer"]

        # 4. Compute Lexical & Text Generation Metrics
        bleu_scores = compute_bleu(generated_answer, ground_truth_answer)
        rouge_scores = compute_rouge(generated_answer, ground_truth_answer)

        # 5. Compute RAGAS Triad Metrics
        faithfulness = evaluate_faithfulness(
            answer=generated_answer,
            context_blocks=retrieved_contexts,
            gemini_client=self.gemini_judge,
        )
        context_prec = evaluate_context_precision(
            question=query,
            retrieved_contexts=retrieved_contexts,
            ground_truth_answer=ground_truth_answer,
            gemini_client=self.gemini_judge,
        )
        context_rec = evaluate_context_recall(
            ground_truth_answer=ground_truth_answer,
            retrieved_contexts=retrieved_contexts,
            gemini_client=self.gemini_judge,
        )

        return {
            "id": sample_id,
            "paper_id": paper_id,
            "paper_title": sample.get("paper_title", ""),
            "question": query,
            "generated_answer": generated_answer,
            "ground_truth_answer": ground_truth_answer,
            "retrieved_chunk_count": len(retrieved_contexts),
            # IR metrics
            "mrr": round(mrr, 4),
            "ndcg_3": round(ndcg_3, 4),
            "ndcg_5": round(ndcg_5, 4),
            "hit_3": round(hit_3, 4),
            "hit_5": round(hit_5, 4),
            # BLEU
            "bleu_1": bleu_scores["bleu_1"],
            "bleu_2": bleu_scores["bleu_2"],
            "bleu_4": bleu_scores["bleu_4"],
            # ROUGE
            "rouge_1_f1": rouge_scores["rouge_1"]["f1"],
            "rouge_2_f1": rouge_scores["rouge_2"]["f1"],
            "rouge_l_f1": rouge_scores["rouge_l"]["f1"],
            # RAGAS Triad
            "faithfulness": round(faithfulness, 4),
            "context_precision": round(context_prec, 4),
            "context_recall": round(context_rec, 4),
        }

    def evaluate_benchmark(
        self,
        dataset: List[Dict[str, Any]],
        top_k: int = 5,
        use_cached_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate full benchmark suite and compute aggregate statistics.
        """
        results: List[Dict[str, Any]] = []
        for i, sample in enumerate(dataset, start=1):
            logger.info(f"Evaluating sample {i}/{len(dataset)}: {sample.get('id', i)}...")
            res = self.evaluate_sample(sample, top_k=top_k, use_cached_run=use_cached_run)
            results.append(res)

        # Aggregate stats
        metric_keys = [
            "mrr",
            "ndcg_3",
            "ndcg_5",
            "hit_3",
            "hit_5",
            "bleu_1",
            "bleu_2",
            "bleu_4",
            "rouge_1_f1",
            "rouge_2_f1",
            "rouge_l_f1",
            "faithfulness",
            "context_precision",
            "context_recall",
        ]

        summary: Dict[str, Dict[str, float]] = {}
        for k in metric_keys:
            vals = [r[k] for r in results if r.get(k) is not None]
            if vals:
                mean_val = float(np.mean(vals))
                std_val = float(np.std(vals))
                summary[k] = {
                    "mean": round(mean_val, 4),
                    "std": round(std_val, 4),
                    "min": round(float(np.min(vals)), 4),
                    "max": round(float(np.max(vals)), 4),
                }

        return {
            "total_samples": len(results),
            "summary": summary,
            "samples": results,
        }

    @staticmethod
    def generate_latex_table(summary: Dict[str, Dict[str, float]]) -> str:
        """
        Generates publication-ready LaTeX table code suitable for direct inclusion in IEEE/ACM/arXiv papers.
        """
        def _fmt(key: str) -> str:
            if key not in summary:
                return "0.0000 $\\pm$ 0.0000"
            m = summary[key]["mean"]
            s = summary[key]["std"]
            return f"{m:.4f} $\\pm$ {s:.4f}"

        latex = r"""\begin{table}[htbp]
\centering
\caption{End-to-End Evaluation of the RESIN Academic RAG Framework across Retrieval, Generation, and Grounding Metrics.}
\label{tab:resin_rag_benchmarks}
\begin{tabular}{l l c}
\hline
\textbf{Evaluation Dimension} & \textbf{Evaluation Metric} & \textbf{Score (Mean $\pm$ Std)} \\
\hline
\multirow{4}{*}{\textbf{Information Retrieval (IR)}}
& MRR (Mean Reciprocal Rank) & """ + _fmt("mrr") + r""" \\
& NDCG@3                     & """ + _fmt("ndcg_3") + r""" \\
& NDCG@5                     & """ + _fmt("ndcg_5") + r""" \\
& Hit@3 / Recall@3           & """ + _fmt("hit_3") + r""" \\
& Hit@5 / Recall@5           & """ + _fmt("hit_5") + r""" \\
\hline
\multirow{6}{*}{\textbf{Text Generation Overlap}}
& BLEU-1                     & """ + _fmt("bleu_1") + r""" \\
& BLEU-2                     & """ + _fmt("bleu_2") + r""" \\
& BLEU-4                     & """ + _fmt("bleu_4") + r""" \\
& ROUGE-1 ($F_1$)            & """ + _fmt("rouge_1_f1") + r""" \\
& ROUGE-2 ($F_1$)            & """ + _fmt("rouge_2_f1") + r""" \\
& ROUGE-L ($F_1$)            & """ + _fmt("rouge_l_f1") + r""" \\
\hline
\multirow{3}{*}{\textbf{RAGAS Triad (Grounding)}}
& Context Precision          & """ + _fmt("context_precision") + r""" \\
& Context Recall             & """ + _fmt("context_recall") + r""" \\
& Faithfulness (Factual Fidelity) & """ + _fmt("faithfulness") + r""" \\
\hline
\end{tabular}
\end{table}"""
        return latex

    @staticmethod
    def generate_markdown_table(summary: Dict[str, Dict[str, float]]) -> str:
        """Generates clean Markdown table for README or project documentation."""
        lines = [
            "| Category | Metric | Mean ± Std | Min | Max |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        categories = {
            "Information Retrieval": ["mrr", "ndcg_3", "ndcg_5", "hit_3", "hit_5"],
            "Lexical Overlap": ["bleu_1", "bleu_2", "bleu_4", "rouge_1_f1", "rouge_2_f1", "rouge_l_f1"],
            "RAGAS Grounding": ["context_precision", "context_recall", "faithfulness"],
        }
        for cat, keys in categories.items():
            for k in keys:
                if k in summary:
                    d = summary[k]
                    lines.append(f"| {cat} | `{k.upper()}` | **{d['mean']:.4f} ± {d['std']:.4f}** | {d['min']:.4f} | {d['max']:.4f} |")
        return "\n".join(lines)

    @staticmethod
    def export_csv(results: List[Dict[str, Any]], filepath: str) -> None:
        """Export sample-by-sample evaluation metrics to CSV file."""
        if not results:
            return
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        keys = list(results[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Exported evaluation CSV to {filepath}")
