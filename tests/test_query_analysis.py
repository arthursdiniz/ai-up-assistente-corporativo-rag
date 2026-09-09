from app.services.llm.base import ConversationMessage
from app.services.query_analysis_service import QueryIntent, QuestionAnalysisService


def test_classifies_supported_task_types() -> None:
    assert QuestionAnalysisService.analyze("Resuma os principais pontos.", False).intent == QueryIntent.SUMMARY
    assert QuestionAnalysisService.analyze("Compare os dois contratos.", False).intent == QueryIntent.COMPARISON
    assert QuestionAnalysisService.analyze("Quais riscos aparecem?", False).intent == QueryIntent.RISK
    assert QuestionAnalysisService.analyze("Monte uma linha do tempo.", False).intent == QueryIntent.TIMELINE
    assert QuestionAnalysisService.analyze("Onde isso está escrito?", True).intent == QueryIntent.LOCATION


def test_ambiguous_question_without_history_requests_clarification() -> None:
    analysis = QuestionAnalysisService.analyze("Explique isso.", False)
    assert analysis.intent == QueryIntent.CLARIFICATION
    assert "sobre qual documento" in analysis.clarification


def test_topic_change_does_not_reuse_history() -> None:
    analysis = QuestionAnalysisService.analyze(
        "Qual é o prazo para solicitar férias?", has_history=True
    )
    assert analysis.uses_history is False


def test_contextualization_keeps_recent_subject() -> None:
    history = [
        ConversationMessage("user", "Apresente a Nexora."),
        ConversationMessage("assistant", "A Nexora é uma empresa de tecnologia."),
    ]
    rewritten = QuestionAnalysisService.contextualize("Pode detalhar melhor?", history)
    assert "Nexora" in rewritten
    assert "Pode detalhar melhor?" in rewritten


def test_generic_entity_reference_uses_the_recent_subject() -> None:
    history = [ConversationMessage("user", "Apresente a empresa Nexora.")]
    analysis = QuestionAnalysisService.analyze(
        "Qual é a missão da empresa?", has_history=True
    )
    assert analysis.uses_history is True


def test_named_company_does_not_reuse_an_unrelated_subject() -> None:
    analysis = QuestionAnalysisService.analyze(
        "Fale sobre a empresa Nexora.", has_history=True
    )
    assert analysis.uses_history is False


def test_contextual_task_asks_model_not_to_repeat_the_previous_answer() -> None:
    analysis = QuestionAnalysisService.analyze(
        "O que mais é importante saber sobre ela?", has_history=True
    )
    instruction = QuestionAnalysisService.task_instruction(analysis)
    assert "no máximo seis tópicos" in instruction
    assert "não repita" in instruction
