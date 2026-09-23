import argparse
import json
import logging
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_runner")

from app.services.rag import RAGService
from app.services.retrieval import RetrievalService
from evaluation.evaluator import RAGEvaluator


def main():
    parser = argparse.ArgumentParser(description="Run Academic Evaluation on RESIN RAG Framework")
    parser.add_argument(
        "--dataset",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "benchmark_dataset.json"),
        help="Path to evaluation benchmark dataset JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "results"),
        help="Directory to save evaluation results, LaTeX tables, and CSVs",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve per question (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of queries to evaluate",
    )
    parser.add_argument(
        "--use-cached",
        action="store_true",
        help="Use cached generated answers if present in dataset instead of live Gemini generation",
    )

    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        logger.error(f"Dataset file not found at: {args.dataset}")
        sys.exit(1)

    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if args.limit:
        dataset = dataset[: args.limit]

    logger.info(f"Loaded {len(dataset)} evaluation benchmark samples from {args.dataset}")

    # Initialize RAG and Retrieval services
    try:
        retrieval_service = RetrievalService()
        rag_service = RAGService(retrieval_service=retrieval_service)
    except Exception as e:
        logger.warning(f"Could not initialize live RAG services ({e}). Running in offline mode.")
        retrieval_service = None
        rag_service = None

    evaluator = RAGEvaluator(
        retrieval_service=retrieval_service,
        rag_service=rag_service,
        gemini_judge_client=None,  # Uses robust heuristic or Gemini when configured
    )

    logger.info("Starting benchmark evaluation...")
    benchmark_res = evaluator.evaluate_benchmark(
        dataset=dataset,
        top_k=args.top_k,
        use_cached_run=args.use_cached,
    )

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Save detailed JSON
    json_path = os.path.join(args.output_dir, "benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_res, f, indent=2)
    logger.info(f"Saved full JSON results to: {json_path}")

    # 2. Save CSV breakdown
    csv_path = os.path.join(args.output_dir, "benchmark_samples.csv")
    evaluator.export_csv(benchmark_res["samples"], csv_path)

    # 3. Save LaTeX table code
    latex_table = evaluator.generate_latex_table(benchmark_res["summary"])
    latex_path = os.path.join(args.output_dir, "paper_table.tex")
    with open(latex_path, "w", encoding="utf-8") as f:
        f.write(latex_table)
    logger.info(f"Saved publication-ready LaTeX table to: {latex_path}")

    # 4. Save Markdown table
    md_table = evaluator.generate_markdown_table(benchmark_res["summary"])
    md_path = os.path.join(args.output_dir, "benchmark_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# RESIN Academic Benchmarks\n\n" + md_table + "\n")
    logger.info(f"Saved Markdown summary table to: {md_path}")

    # Print summary to terminal
    print("\n" + "=" * 65)
    print("RESIN ACADEMIC RAG BENCHMARK EVALUATION RESULTS")
    print("=" * 65)
    print(md_table)
    print("=" * 65)
    print(f"\nLaTeX Table Code ready for your research paper:\n")
    print(latex_table)
    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
