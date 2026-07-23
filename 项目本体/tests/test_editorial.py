from app.services.editorial import review_content, rewrite_content


def test_editorial_review_flags_generic_and_unsupported_claims() -> None:
    content = (
        "值得注意的是，这是一项重大突破。\n\n"
        "[测试来源：AI Agent 更新](https://example.com/agent)（测试作者，2026-07-23）指出了工具调用的变化。\n\n"
        "此外，这一变化可能颠覆行业。"
    )

    review = review_content(content)

    assert review.factual_statement_count >= 1
    assert review.sourced_paragraph_ratio == 33
    assert review.unsupported_judgments
    assert review.generic_sentences
    assert review.strong_conclusions


def test_safe_rewrite_preserves_source_links_and_does_not_add_content() -> None:
    content = "这是一项重大突破。\n\n[测试来源](https://example.com/source)"

    rewritten = rewrite_content(content, "更克制")

    assert "重大" not in rewritten
    assert "值得关注" in rewritten
    assert "[测试来源](https://example.com/source)" in rewritten
