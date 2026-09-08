import pytest
from app.agent.formatter import (
    clean_markdown_output,
    detect_question_intent,
    get_intent_formatting_instructions,
)


def test_intent_detection_comprehensive():
    assert detect_question_intent("What is this paper about?") == "overview"
    assert detect_question_intent("What is the main idea?") == "overview"
    assert detect_question_intent("Summarize this paper.") == "summary"
    assert detect_question_intent("What methods are used?") == "methods"
    assert detect_question_intent("What were the results?") == "results"
    assert detect_question_intent("How does the model perform?") == "results"
    assert detect_question_intent("What are the limitations?") == "limitations"
    assert detect_question_intent("Compare these two methods.") == "comparison"
    assert detect_question_intent("What is RAGAS?") == "definition"
    assert detect_question_intent("Define RAGAS.") == "definition"
    assert detect_question_intent("What does RAGAS mean?") == "definition"
    assert detect_question_intent("What is the definition of RAGAS?") == "definition"
    assert detect_question_intent("Explain how RAG works.") == "explanation"
    assert detect_question_intent("What dataset was used?") == "dataset"
    assert detect_question_intent("What are the main contributions?") == "contributions"
    assert detect_question_intent("Hello, can you help me?") == "general"


def test_escaped_markdown():
    raw = "\\* \\*\\*RAGAS:\\*\\* explanation"
    cleaned = clean_markdown_output(raw)
    assert cleaned == "- **RAGAS:** explanation"


def test_escaped_heading():
    raw = "\\# Methods"
    cleaned = clean_markdown_output(raw)
    assert cleaned == "# Methods"


def test_heading_and_bullet_on_same_line():
    raw = "### Key Aspects - **Method A:** explanation - **Method B:** explanation"
    cleaned = clean_markdown_output(raw)
    assert "### Key Aspects" in cleaned
    assert "- **Method A:**" in cleaned
    assert "- **Method B:**" in cleaned
    # Ensure linebreaks separate them
    assert "\n" in cleaned


def test_preamble_removal():
    raw = "Based on the provided context, the paper proposes RAGAS..."
    cleaned = clean_markdown_output(raw)
    assert cleaned == "the paper proposes RAGAS..."

    raw2 = "According to the retrieved context, the dataset contains 10,000 samples."
    cleaned2 = clean_markdown_output(raw2)
    assert cleaned2 == "the dataset contains 10,000 samples."


def test_internal_tag_cleanup():
    raw = "[Section: Main Content]"
    cleaned = clean_markdown_output(raw)
    assert "[Section: Main Content]" not in cleaned
    assert "Section: Main Content" in cleaned


def test_latex_preservation():
    raw = "The loss function is $\\frac{1}{2}mv^2$ and display math $$ \\alpha + \\beta $$."
    cleaned = clean_markdown_output(raw)
    assert "$\\frac{1}{2}mv^2$" in cleaned
    assert "$$ \\alpha + \\beta $$" in cleaned


def test_code_preservation():
    raw = "Here is Python code:\n```python\nprint(\"\\*literal\")\n```"
    cleaned = clean_markdown_output(raw)
    assert "```python\nprint(\"\\*literal\")\n```" in cleaned


def test_inline_code_preservation():
    raw = "Use the function `print(\"\\*literal\")` to log."
    cleaned = clean_markdown_output(raw)
    assert "`print(\"\\*literal\")`" in cleaned


def test_url_preservation():
    raw = "See paper at https://example.com/a_b?param=1&other=2 for details."
    cleaned = clean_markdown_output(raw)
    assert "https://example.com/a_b?param=1&other=2" in cleaned


def test_normal_markdown_preservation():
    raw = "### Methods\n\n1. **Method A** — explanation\n2. **Method B** — explanation"
    cleaned = clean_markdown_output(raw)
    assert "### Methods" in cleaned
    assert "1. **Method A**" in cleaned
    assert "2. **Method B**" in cleaned


def test_empty_and_null_input():
    assert clean_markdown_output(None) == ""
    assert clean_markdown_output("") == ""
    assert clean_markdown_output("   ") == ""
