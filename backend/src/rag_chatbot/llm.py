"""LLM access through LangChain. Gemini (free tier) or OpenAI, chosen by LLM_PROVIDER in .env."""
from __future__ import annotations

import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .config import LLM_MODEL, MAX_TOKENS, PROVIDER, TEMPERATURE

GEMINI_KEY_HELP = (
    "GOOGLE_API_KEY not found. Get a free key at https://aistudio.google.com/apikey "
    "and add it to backend/.env"
)


def get_llm(max_tokens: int = MAX_TOKENS):
    if PROVIDER == "gemini":
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(GEMINI_KEY_HELP)
        from langchain_google_genai import ChatGoogleGenerativeAI

        # No max_output_tokens or temperature here: Gemini 3 models count their internal
        # "thinking" tokens against the limit (small limits give empty answers), and Google
        # recommends the default temperature.
        return ChatGoogleGenerativeAI(model=LLM_MODEL, google_api_key=key)

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not found. Copy .env.example to .env and add your key.")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=LLM_MODEL, temperature=TEMPERATURE, max_tokens=max_tokens)


def complete(system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
    """One system + user prompt in, plain text out (prompt | llm | parser)."""
    # {system} / {user} are filled in as variables, so braces inside the text are harmless
    prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])
    chain = prompt | get_llm(max_tokens) | StrOutputParser()
    return chain.invoke({"system": system, "user": user})