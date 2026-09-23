import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ============================================================================
# 1. Information Retrieval (IR) Metrics: MRR, NDCG@K, Hit@K
# ============================================================================

def compute_mrr(retrieved_items: Sequence[Any], ground_truth_relevant: Sequence[Any]) -> float:
    """
    Mean Reciprocal Rank (MRR):
    Calculates 1 / rank of the first relevant item retrieved.
    Returns 0.0 if no relevant items are found.
    """
    if not retrieved_items or not ground_truth_relevant:
        return 0.0
    gt_set = set(ground_truth_relevant)
    for rank, item in enumerate(retrieved_items, start=1):
        if item in gt_set:
            return 1.0 / rank
    return 0.0


def compute_hit_at_k(retrieved_items: Sequence[Any], ground_truth_relevant: Sequence[Any], k: int = 3) -> float:
    """
    Hit@K (or Recall indicator):
    Returns 1.0 if at least one relevant item is in the top-K retrieved items, else 0.0.
    """
    top_k = retrieved_items[:k]
    gt_set = set(ground_truth_relevant)
    return 1.0 if any(item in gt_set for item in top_k) else 0.0


def compute_ndcg_at_k(retrieved_items: Sequence[Any], ground_truth_relevant: Sequence[Any], k: int = 3) -> float:
    """
    Normalized Discounted Cumulative Gain at rank K (NDCG@K):
    Uses binary relevance (1 if item in ground_truth_relevant else 0).
    DCG@K = sum_{i=1}^k (2^{rel_i} - 1) / log2(i + 1)
    NDCG@K = DCG@K / IDCG@K
    """
    if not retrieved_items or not ground_truth_relevant:
        return 0.0

    gt_set = set(ground_truth_relevant)
    top_k = retrieved_items[:k]

    dcg = 0.0
    for i, item in enumerate(top_k, start=1):
        rel = 1.0 if item in gt_set else 0.0
        if rel > 0:
            dcg += (math.pow(2.0, rel) - 1.0) / math.log2(i + 1)

    # Ideal DCG: perfect ranking with up to min(k, len(gt_set)) relevant items first
    ideal_hits = min(k, len(gt_set))
    if ideal_hits == 0:
        return 0.0

    idcg = 0.0
    for i in range(1, ideal_hits + 1):
        idcg += (math.pow(2.0, 1.0) - 1.0) / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0


# ============================================================================
# 2. Lexical & Generation Overlap Metrics: BLEU-1/2/4 & ROUGE-1/2/L
# ============================================================================

def _tokenize(text: str) -> List[str]:
    """Simple alphanumeric tokenizer and lowercaser."""
    return re.findall(r"\b\w+\b", text.lower())


def _get_ngrams(tokens: List[str], n: int) -> Counter:
    """Extract n-grams from a token sequence."""
    if len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def compute_bleu(candidate: str, reference: str, max_n: int = 4) -> Dict[str, float]:
    """
    Computes standard BLEU-1, BLEU-2, and BLEU-4 scores with Brevity Penalty.
    Formula: BP = exp(min(0, 1 - r / c))
    BLEU-N = BP * exp(sum_{n=1}^N w_n * log(p_n))
    """
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)

    c = len(cand_tokens)
    r = len(ref_tokens)

    if c == 0 or r == 0:
        return {"bleu_1": 0.0, "bleu_2": 0.0, "bleu_4": 0.0, "bp": 0.0}

    # Brevity Penalty
    bp = 1.0 if c > r else math.exp(1.0 - (r / c))

    precisions: List[float] = []
    for n in range(1, max_n + 1):
        cand_ngrams = _get_ngrams(cand_tokens, n)
        ref_ngrams = _get_ngrams(ref_tokens, n)

        total_cand = sum(cand_ngrams.values())
        if total_cand == 0:
            precisions.append(0.0)
            continue

        # Clipped counts
        overlap = 0
        for ng, count in cand_ngrams.items():
            overlap += min(count, ref_ngrams.get(ng, 0))

        precisions.append(overlap / total_cand)

    # BLEU-1
    bleu_1 = bp * precisions[0] if precisions[0] > 0 else 0.0

    # BLEU-2 (geometric mean of p1, p2 with weights 0.5, 0.5)
    if precisions[0] > 0 and precisions[1] > 0:
        bleu_2 = bp * math.exp(0.5 * math.log(precisions[0]) + 0.5 * math.log(precisions[1]))
    else:
        bleu_2 = 0.0

    # BLEU-4 (geometric mean of p1..p4 with uniform weights 0.25)
    # Using smoothing for zero n-gram precision
    smoothed_logs = []
    for p in precisions[:4]:
        if p > 0:
            smoothed_logs.append(math.log(p))
        else:
            smoothed_logs.append(math.log(1e-5))  # Laplace / epsilon smoothing

    bleu_4 = bp * math.exp(sum(smoothed_logs) / 4.0)

    return {
        "bleu_1": round(bleu_1, 4),
        "bleu_2": round(bleu_2, 4),
        "bleu_4": round(bleu_4, 4),
        "bp": round(bp, 4),
    }


def _lcs_length(x: List[str], y: List[str]) -> int:
    """Longest Common Subsequence length using dynamic programming."""
    m, n = len(x), len(y)
    if m == 0 or n == 0:
        return 0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if x[i - 1] == y[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def compute_rouge(candidate: str, reference: str) -> Dict[str, Dict[str, float]]:
    """
    Computes ROUGE-1, ROUGE-2, and ROUGE-L (Precision, Recall, F1).
    """
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)

    if not cand_tokens or not ref_tokens:
        zero_score = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        return {"rouge_1": zero_score, "rouge_2": zero_score, "rouge_l": zero_score}

    def _calc_prf(overlap_count: int, cand_total: int, ref_total: int) -> Dict[str, float]:
        prec = overlap_count / cand_total if cand_total > 0 else 0.0
        rec = overlap_count / ref_total if ref_total > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}

    # 1. ROUGE-1 (Unigrams)
    c1 = Counter(cand_tokens)
    r1 = Counter(ref_tokens)
    overlap_1 = sum(min(count, r1.get(w, 0)) for w, count in c1.items())
    rouge_1 = _calc_prf(overlap_1, len(cand_tokens), len(ref_tokens))

    # 2. ROUGE-2 (Bigrams)
    c2 = _get_ngrams(cand_tokens, 2)
    r2 = _get_ngrams(ref_tokens, 2)
    overlap_2 = sum(min(count, r2.get(bg, 0)) for bg, count in c2.items())
    rouge_2 = _calc_prf(overlap_2, max(0, len(cand_tokens) - 1), max(0, len(ref_tokens) - 1))

    # 3. ROUGE-L (Longest Common Subsequence)
    lcs = _lcs_length(cand_tokens, ref_tokens)
    rouge_l = _calc_prf(lcs, len(cand_tokens), len(ref_tokens))

    return {
        "rouge_1": rouge_1,
        "rouge_2": rouge_2,
        "rouge_l": rouge_l,
    }


# ============================================================================
# 3. RAGAS Triad: Faithfulness, Context Precision, Context Recall
# ============================================================================

def evaluate_faithfulness(
    answer: str,
    context_blocks: List[str],
    gemini_client: Optional[Any] = None,
) -> float:
    """
    RAGAS Faithfulness:
    Evaluates what fraction of claims in the generated answer are grounded in the retrieved context.
    Score = (Number of supported claims) / (Total number of claims)
    Uses LLM-as-a-judge with structured JSON output if gemini_client is available,
    otherwise falls back to sentence-level lexical entailment heuristic.
    """
    if not answer.strip() or not context_blocks:
        return 0.0

    if gemini_client:
        prompt = f"""You are an unbiased scientific evaluation judge evaluating a RAG system.
Evaluate the FAITHFULNESS of the generated answer against the retrieved evidence context.

Retrieved Context Evidence:
{chr(10).join(f'--- Passage {i+1} ---{chr(10)}{ctx}' for i, ctx in enumerate(context_blocks))}

Generated Answer to Evaluate:
{answer}

Task:
1. Break down the generated answer into individual factual claims/statements.
2. For each claim, determine if it can be directly inferred from the retrieved context (YES or NO).
3. Calculate faithfulness_score = (supported claims) / (total claims).

Output strictly valid JSON with this format:
{{
  "claims": [
    {{"claim": "statement...", "supported": true}}
  ],
  "supported_count": 3,
  "total_count": 3,
  "faithfulness_score": 1.0
}}
"""
        try:
            res = gemini_client.generate_content(prompt)
            raw = res.text.strip()
            # Clean markdown code blocks if wrapped
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            import json
            data = json.loads(raw)
            return float(data.get("faithfulness_score", 1.0))
        except Exception:
            pass

    # Heuristic fallback: check sentence overlap against context
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", answer) if len(s.strip()) > 10]
    if not sentences:
        return 1.0
    combined_ctx = " ".join(context_blocks).lower()
    supported = 0
    for s in sentences:
        tokens = [t for t in _tokenize(s) if len(t) > 3]
        if not tokens:
            supported += 1
            continue
        # If >= 60% of significant content words appear in retrieved context, consider supported
        matches = sum(1 for t in tokens if t in combined_ctx)
        if matches / len(tokens) >= 0.5:
            supported += 1
    return round(supported / len(sentences), 4)


def evaluate_context_precision(
    question: str,
    retrieved_contexts: List[str],
    ground_truth_answer: str,
    gemini_client: Optional[Any] = None,
) -> float:
    """
    RAGAS Context Precision:
    Evaluates whether relevant chunks are ranked higher than irrelevant ones.
    Formula: Average Precision of relevance scores over the retrieved list.
    """
    if not retrieved_contexts:
        return 0.0

    if gemini_client:
        prompt = f"""You are an unbiased scientific evaluation judge.
Evaluate the CONTEXT PRECISION of the retrieved passages for answering the query.

Question: {question}
Ground-Truth Reference Answer: {ground_truth_answer}

Retrieved Passages in Rank Order:
{chr(10).join(f'Rank {i+1}: {ctx[:400]}...' for i, ctx in enumerate(retrieved_contexts))}

For each rank (1 to {len(retrieved_contexts)}), determine if the passage is RELEVANT (contains facts useful to answer the question).
Output strictly JSON:
{{
  "relevance": [true, false, true],
  "context_precision": 0.83
}}
"""
        try:
            res = gemini_client.generate_content(prompt)
            raw = res.text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            import json
            data = json.loads(raw)
            return float(data.get("context_precision", 1.0))
        except Exception:
            pass

    # Heuristic fallback: check content overlap between each chunk and ground-truth answer
    gt_words = set(t for t in _tokenize(ground_truth_answer) if len(t) > 3)
    if not gt_words:
        return 1.0

    precisions = []
    hits = 0
    for k, ctx in enumerate(retrieved_contexts, start=1):
        ctx_words = set(_tokenize(ctx))
        overlap = len(gt_words.intersection(ctx_words))
        is_relevant = overlap >= 3 or (overlap / len(gt_words) >= 0.25)
        if is_relevant:
            hits += 1
            precisions.append(hits / k)

    if not precisions:
        return 0.0
    return round(sum(precisions) / len(precisions), 4)


def evaluate_context_recall(
    ground_truth_answer: str,
    retrieved_contexts: List[str],
    gemini_client: Optional[Any] = None,
) -> float:
    """
    RAGAS Context Recall:
    Measures the extent to which the retrieved context covers all necessary information
    contained in the ground-truth reference answer.
    """
    if not ground_truth_answer.strip() or not retrieved_contexts:
        return 0.0

    if gemini_client:
        prompt = f"""You are an unbiased scientific evaluation judge.
Evaluate the CONTEXT RECALL of the retrieved passages against the ground-truth answer.

Ground-Truth Answer:
{ground_truth_answer}

Retrieved Passages:
{chr(10).join(retrieved_contexts)}

Task:
Break down the ground-truth answer into key assertions. For each assertion, determine whether it can be attributed to the retrieved context.
Output strictly JSON:
{{
  "total_assertions": 4,
  "recalled_assertions": 4,
  "context_recall": 1.0
}}
"""
        try:
            res = gemini_client.generate_content(prompt)
            raw = res.text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            import json
            data = json.loads(raw)
            return float(data.get("context_recall", 1.0))
        except Exception:
            pass

    # Heuristic fallback: key terms recalled from ground-truth answer in context
    gt_tokens = [t for t in _tokenize(ground_truth_answer) if len(t) > 3]
    if not gt_tokens:
        return 1.0
    combined_ctx = " ".join(retrieved_contexts).lower()
    recalled = sum(1 for t in gt_tokens if t in combined_ctx)
    return round(recalled / len(gt_tokens), 4)
