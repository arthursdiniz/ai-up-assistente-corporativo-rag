from app.services.generation_guard import GenerationGuard


def test_does_not_guess_a_replacement_for_identifier() -> None:
    corrected = GenerationGuard.preserve_shared_identifiers(
        "O contrato ZX-90 tem prazo de 45 dias.",
        "Qual é o prazo do contrato ZX-900?",
        ["O contrato ZX-900 tem prazo de 45 dias."],
    )
    assert corrected == "O contrato ZX-90 tem prazo de 45 dias."


def test_does_not_add_identifier_that_is_not_in_document_context() -> None:
    answer = "Não encontrei o contrato solicitado."
    assert GenerationGuard.preserve_shared_identifiers(
        answer,
        "Qual é o prazo do contrato ZX-900?",
        ["O contrato AB-100 tem prazo de 10 dias."],
    ) == answer


def test_preserves_already_correct_identifier_without_rewriting_answer() -> None:
    answer = "O contrato ZX-900 tem prazo de 45 dias."
    assert GenerationGuard.preserve_shared_identifiers(
        answer,
        "Qual é o prazo do contrato ZX-900?",
        ["O contrato ZX-900 tem prazo de 45 dias."],
    ) == answer


def test_limits_overgenerated_markdown_list_to_complete_items() -> None:
    answer = "Resumo:\n" + "\n".join(f"- Item {index}." for index in range(1, 9))
    limited = GenerationGuard.limit_list_items(answer, 6)
    assert "Item 6." in limited
    assert "Item 7." not in limited
    assert limited.endswith("Item 6.")
