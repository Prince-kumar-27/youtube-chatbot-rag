import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from rag_chatbot import config
from rag_chatbot.generator import answer_question, build_context
from rag_chatbot.llm import complete, get_llm
from rag_chatbot.models import Chunk
from rag_chatbot.retriever import Retriever
from rag_chatbot.utils import format_timestamp


def make_fake_llm(seen, reply="answer [00:10]"):
    """A stand-in for ChatOpenAI that records the prompt it receives."""
    def fake(prompt_value):
        seen["prompt"] = prompt_value.to_string()
        return AIMessage(content=reply)

    return RunnableLambda(fake)


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(75) == "01:15"
    assert format_timestamp(3725) == "1:02:05"


def test_context_labels_each_chunk_with_timestamp():
    context = build_context([Chunk("first", 5.0), Chunk("second", 125.0)])
    assert "[00:05]\nfirst" in context
    assert "[02:05]\nsecond" in context


def test_chain_returns_answer_and_sources_in_video_order():
    chunks = [Chunk("later part about cats", 300.0), Chunk("early part about dogs", 10.0)]
    seen = {}
    result = answer_question(Retriever(chunks), "tell me about dogs", k=2, llm=make_fake_llm(seen))

    assert result.text == "answer [00:10]"
    assert [c.start for c in result.sources] == [10.0, 300.0]
    assert config.QA_SYSTEM_PROMPT in seen["prompt"]
    assert "tell me about dogs" in seen["prompt"]
    assert seen["prompt"].index("[00:10]") < seen["prompt"].index("[05:00]")


def test_prompt_tells_model_to_admit_when_it_does_not_know():
    assert config.NO_ANSWER_TEXT in config.QA_SYSTEM_PROMPT


def test_braces_in_text_do_not_break_the_prompt():
    chunks = [Chunk("code looks like {x: 1} and {y}", 1.0)]
    seen = {}
    answer_question(Retriever(chunks), "what is {x}?", llm=make_fake_llm(seen))
    assert "{x: 1}" in seen["prompt"]


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_llm()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        complete("system", "user")


def test_complete_passes_system_and_user_text_through(monkeypatch):
    from rag_chatbot import llm

    seen = {}
    monkeypatch.setattr(llm, "get_llm", lambda max_tokens=0: make_fake_llm(seen, reply="done"))
    assert complete("be brief {not a variable}", "hello {y}") == "done"
    assert "be brief {not a variable}" in seen["prompt"] and "hello {y}" in seen["prompt"]
