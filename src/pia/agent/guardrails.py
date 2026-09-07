"""Generic catalog-scope string filters. Capability restriction is the hard control."""

from __future__ import annotations

import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

REFUSAL = "I can only help with products, reviews, and comparisons in this catalog."

_REFUSE = [
    re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I),
    re.compile(r"reveal (your )?(system )?prompt", re.I),
    re.compile(r"show (me )?(the )?(system )?prompt", re.I),
    re.compile(r"api[_ ]?key|groq_api_key|service[_ ]role", re.I),
    re.compile(r"scrape (this |the )?(url|site|amazon|page)", re.I),
    re.compile(r"open this url|fetch this url|http://|https://", re.I),
    re.compile(r"amazon\.com|other retailer", re.I),
    re.compile(r"\bweather\b", re.I),
    re.compile(r"\b(drop table|union select|;--)\b", re.I),
    re.compile(r"\b(powershell|bash -c|/bin/sh)\b", re.I),
    re.compile(r"bypass captcha", re.I),
    re.compile(r"write (me )?(a )?(python|javascript) (script|program)", re.I),
]

_SECRET = [
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\."),
]

_PROMPT_LEAK = re.compile(
    r"You are a Petbarn catalog assistant for a technical assessment",
    re.I,
)


def last_human_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def input_refusal(text: str) -> str | None:
    if not text:
        return None
    for pattern in _REFUSE:
        if pattern.search(text):
            return REFUSAL
    return None


def output_is_leaky(text: str) -> bool:
    if not text:
        return False
    if _PROMPT_LEAK.search(text):
        return True
    return any(pattern.search(text) for pattern in _SECRET)


class GuardrailMiddleware(AgentMiddleware):
    """Keyword refuses plus output leak scan. Not a semantic classifier."""

    def wrap_model_call(self, request, handler):
        text = last_human_text(list(request.messages))
        refused = input_refusal(text)
        if refused:
            return AIMessage(content=refused)
        response = handler(request)
        message = response if isinstance(response, AIMessage) else getattr(response, "result", None)
        content = message.content if isinstance(message, AIMessage) else ""
        if isinstance(content, str) and output_is_leaky(content):
            return AIMessage(content=REFUSAL)
        return response

    def wrap_tool_call(self, request, handler):
        call = getattr(request, "tool_call", None) or {}
        if isinstance(call, dict):
            tool_name = call.get("name") or ""
            args = str(call.get("args") or "")
            call_id = str(call.get("id") or "blocked")
        else:
            tool_name = getattr(request, "name", "") or ""
            args = str(getattr(request, "args", "") or call)
            call_id = str(getattr(request, "tool_call_id", None) or "blocked")
        blob = f"{tool_name} {args}".lower()
        if "http://" in blob or "https://" in blob or "playwright" in blob:
            return ToolMessage(content=REFUSAL, tool_call_id=call_id)
        result = handler(request)
        if isinstance(result, ToolMessage) and output_is_leaky(str(result.content)):
            return ToolMessage(content=REFUSAL, tool_call_id=result.tool_call_id)
        return result
