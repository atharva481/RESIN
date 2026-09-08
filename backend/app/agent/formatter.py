import re
from typing import List, Tuple, Dict, Any

# ---------------------------------------------------------------------------
# Task 2: Deterministic Question Intent Classifier
# ---------------------------------------------------------------------------
def detect_question_intent(question: str) -> str:
    """
    Classify user question into intent categories using deterministic regex/keyword patterns.
    Supported intents: overview, summary, methods, results, limitations, comparison,
    explanation, definition, dataset, contributions, general.
    """
    if not question or not isinstance(question, str) or not question.strip():
        return "general"

    q_raw = question.lower().strip()
    q_clean = re.sub(r"[^\w\s]", "", q_raw).strip()

    # Overview intent
    if re.search(r"\b(what is this paper about|main idea|high level|overview|what does this paper do)\b", q_clean):
        return "overview"

    # Summary intent
    if re.search(r"\b(summarize|summary|digest|synopsis|executive summary)\b", q_clean):
        return "summary"

    # Comparison intent
    if re.search(r"\b(compare|comparison|versus|vs|difference|differ|how does .* compare)\b", q_clean):
        return "comparison"

    # Definition intent
    if re.search(r"\b(define|definition of|what is [a-z0-9_]+$|what (is|does|are) (a |the )?([a-z0-9_]+) (mean|stand for|define))\b", q_clean):
        return "definition"



    # Results intent
    if re.search(r"\b(results?|findings?|performance|accuracy|scores?|benchmarks?|evaluat|metrics?|how well|how does .* perform)\b", q_clean):
        return "results"

    # Explanation intent
    if re.search(r"\b(explain|how (does|do) .* work|why did|concept of|describe how)\b", q_clean):
        return "explanation"

    # Methods intent
    if re.search(r"\b(methods?|methodology|approaches|approach|techniques?|architecture|algorithm|model|how (did|do) they (build|train|implement|design))\b", q_clean):
        return "methods"

    # Limitations intent
    if re.search(r"\b(limitations?|drawbacks?|weaknesses?|shortcomings?|future work|trade[- ]offs?)\b", q_clean):
        return "limitations"

    # Dataset intent
    if re.search(r"\b(datasets?|data set|corpus|data sources?|benchmark datasets?|training data)\b", q_clean):
        return "dataset"

    # Contributions intent
    if re.search(r"\b(contributions?|novelty|what is new|key takeaways?|main impact)\b", q_clean):
        return "contributions"


    return "general"


# ---------------------------------------------------------------------------
# Task 3: Intent-Specific Formatting Instructions for Prompt
# ---------------------------------------------------------------------------
def get_intent_formatting_instructions(intent: str) -> str:
    """Return presentation formatting guidance tailored to the detected question intent."""
    instructions: Dict[str, str] = {
        "overview": (
            "Formatting Directive (Overview):\n"
            "- ### Overview (2-4 sentence summary)\n"
            "- ### Main Goal (What problem the paper addresses)\n"
            "- ### Key Idea (Core innovation)\n"
            "- ### Takeaway (One sentence conclusion)\n"
            "Keep it crisp and scannable. Do not add unnecessary sections."
        ),
        "summary": (
            "Formatting Directive (Summary):\n"
            "- ### Summary (Brief overview)\n"
            "- Include bullet points for: Problem, Approach, Results, Key Takeaway.\n"
            "Include only sections supported by evidence."
        ),
        "methods": (
            "Formatting Directive (Methods):\n"
            "- ### Methods\n"
            "  1. **Method Name** — Concise explanation of how it works.\n"
            "  2. **Method Name** — Concise explanation.\n"
            "- ### Why These Methods Are Used (Short justification if available)."
        ),
        "results": (
            "Formatting Directive (Results):\n"
            "- ### Results\n"
            "  - **Finding 1:** Quantitative or qualitative result.\n"
            "  - **Finding 2:** Key benchmark performance.\n"
            "Include exact numerical metrics when supported by evidence. Do not invent numbers."
        ),
        "limitations": (
            "Formatting Directive (Limitations):\n"
            "- ### Limitations\n"
            "  - Bullet list of explicit limitations, assumptions, or trade-offs mentioned in the paper."
        ),
        "comparison": (
            "Formatting Directive (Comparison):\n"
            "Use a Markdown comparison table when evaluating multiple papers or approaches:\n"
            "| Aspect | Paper / Method A | Paper / Method B |\n"
            "|---|---|---|\n"
            "| Goal | ... | ... |\n"
            "| Method | ... | ... |\n"
            "| Results | ... | ... |\n"
            "Summarize key differences below the table."
        ),
        "explanation": (
            "Formatting Directive (Explanation):\n"
            "- ### Simple Explanation (Plain language introduction)\n"
            "- ### How It Works (Numbered step-by-step sequence)\n"
            "- ### In This Paper (How the paper applies this concept)"
        ),
        "definition": (
            "Formatting Directive (Definition):\n"
            "Answer directly in 1-2 paragraphs without heavy headings.\n"
            "Example: '**Term** refers to...'\n"
            "Provide clear, direct context."
        ),
        "dataset": (
            "Formatting Directive (Dataset):\n"
            "- ### Dataset\n"
            "  - **Name & Origin:** ...\n"
            "  - **Size & Format:** ...\n"
            "  - **Purpose:** ..."
        ),
        "contributions": (
            "Formatting Directive (Contributions):\n"
            "- ### Main Contributions\n"
            "  1. **First Contribution** — ...\n"
            "  2. **Second Contribution** — ..."
        ),
        "general": (
            "Formatting Directive:\n"
            "Answer directly with concise paragraphs (2-4 sentences). Use headings (`### Heading`) and bullet points only when they improve scannability."
        ),
    }
    return instructions.get(intent, instructions["general"])


# ---------------------------------------------------------------------------
# Task 7: Defensive Markdown Sanitizer (LaTeX, Code & URL Safe)
# ---------------------------------------------------------------------------
def clean_markdown_output(text: str) -> str:
    """
    Defensive fallback sanitizer to clean malformed Markdown artifacts.
    Safe against corrupting LaTeX math ($...$, $$...$$), code blocks (```...```),
    inline code (`...`), URLs, and legitimate backslashes.
    """
    if not text or not isinstance(text, str) or not text.strip():
        return "" if text is not None else ""

    # Step 1: Protect fenced code blocks (```...```) and math environments ($$...$$ and $...$)
    protected_blocks: List[str] = []

    def save_block(match: re.Match) -> str:
        protected_blocks.append(match.group(0))
        return f"___PROTECTED_BLOCK_{len(protected_blocks) - 1}___"

    # Match fenced code blocks
    processed = re.sub(r"```[\s\S]*?```", save_block, text)
    # Match display math $$...$$
    processed = re.sub(r"\$\$[\s\S]*?\$\$", save_block, processed)
    # Match inline math $...$
    processed = re.sub(r"\$[^\$\n]+?\$", save_block, processed)
    # Match inline code `...`
    processed = re.sub(r"`[^`\n]+?`", save_block, processed)

    # Step 2: Remove preamble introductory phrases at start of text or lines
    preamble_patterns = [
        r"^(?:Based on the (?:provided|retrieved|available) (?:context|paper|documents?|information),?\s*)",
        r"^(?:According to the (?:provided|retrieved|available) (?:context|paper|documents?|information),?\s*)",
        r"^(?:From the (?:provided|retrieved|available) (?:context|paper|documents?|information),?\s*)",
        r"^(?:The provided context indicates that,?\s*)",
        r"^(?:I found that,?\s*)",
    ]
    for pat in preamble_patterns:
        processed = re.sub(pat, "", processed, flags=re.IGNORECASE | re.MULTILINE)

    # Step 3: Fix heading and inline bullet layout artifacts
    # Heading & bullet on same line: "### Heading - **Item**" -> "### Heading\n\n- **Item**"
    processed = re.sub(r"^(#{1,6}\s+[^\n]+?)\s+-\s+(\*\*|[A-Za-z0-9])", r"\1\n\n- \2", processed, flags=re.MULTILINE)

    # Multiple inline bullets on same line: "... - **Item B**" -> "...\n- **Item B**"
    processed = re.sub(r"([^\n])\s+-\s+\*\*", r"\1\n- **", processed)

    # Step 4: Fix escaped malformed markdown list & heading artifacts:
    # e.g., "\### Heading" -> "### Heading"
    # e.g., "\* \*\*Methods\*\*" -> "- **Methods**"
    # e.g., "\* \*\*Text\*\*" -> "- **Text**"
    processed = re.sub(r"^\\\s*(#{1,6}\s+)", r"\1", processed, flags=re.MULTILINE)
    processed = re.sub(r"^\\\*\s+\\\*\\\*", "- **", processed, flags=re.MULTILINE)
    processed = re.sub(r"^\\\*\s+", "- ", processed, flags=re.MULTILINE)
    processed = re.sub(r"^\\\#{1,6}\s+", "# ", processed, flags=re.MULTILINE)

    # Clean double escaped asterisks: "\*\*Text\*\*" -> "**Text**"
    processed = re.sub(r"\\\*\\\*", "**", processed)

    # Step 5: Clean internal metadata tags like "[Section: Main Content]" -> "Section: Main Content"
    processed = re.sub(r"\[Section:\s*([^\]]+)\]", r"Section: \1", processed)

    # Step 6: Restore protected code blocks & math environments
    for idx, original_block in enumerate(protected_blocks):
        processed = processed.replace(f"___PROTECTED_BLOCK_{idx}___", original_block)

    return processed.strip()
