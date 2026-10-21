"""Step 3: the question-answering chain (retrieve -> augment -> generate), built with LCEL."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

from .config import DEFAULT_TOP_K, QA_SYSTEM_PROMPT
from .llm import get_llm
from .models import Chunk
from .retriever import Retriever
from .utils import format_timestamp

QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system}"),
    ("human", "Transcript excerpts:\n{context}\n\nQuestion: {question}"),
]).partial(system=QA_SYSTEM_PROMPT)


@dataclass
class Answer:
    text: str
    sources: list[Chunk]


def build_context(chunks: list[Chunk]) -> str:
    """Label each excerpt with its timestamp so the model can cite it."""
    return "\n\n".join(f"[{format_timestamp(c.start)}]\n{c.text}" for c in chunks)


def build_qa_chain(retriever: Retriever, llm, k: int = DEFAULT_TOP_K):
    """question -> {sources, question} -> prompt -> llm -> text, keeping the sources.

        parallel step:  sources  = retrieve(question)      question = question
        then:           answer   = prompt(context, question) | llm | parser
    """
    def retrieve(question: str) -> list[Chunk]:
        # Present excerpts in video order, which is easier for the model to follow
        return sorted(retriever.search(question, k), key=lambda c: c.start)

    answer_chain = (
        RunnableLambda(lambda x: {"context": build_context(x["sources"]), "question": x["question"]})
        | QA_PROMPT
        | llm
        | StrOutputParser()
    )
    return (
        RunnableParallel(sources=RunnableLambda(retrieve), question=RunnablePassthrough())
        | RunnablePassthrough.assign(answer=answer_chain)
    )


def answer_question(retriever: Retriever, question: str, k: int = DEFAULT_TOP_K, llm=None) -> Answer:
    result = build_qa_chain(retriever, llm or get_llm(), k).invoke(question)
    return Answer(text=result["answer"], sources=result["sources"])
