"""Pydantic models at the persistence and tool boundary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

SourceType = Literal["petbarn_snapshot", "synthetic_sample"]
MessageRole = Literal["user", "assistant", "tool"]
RunStatus = Literal["queued", "running", "completed", "failed"]
ToolStatus = Literal["running", "success", "error"]


class ProductInput(BaseModel):
    sku: str
    name: str
    url: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = "AUD"
    availability: str | None = None
    rating_value: float | None = None
    review_count: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewInput(BaseModel):
    sku: str
    rating: int
    external_review_id: str | None = None
    title: str | None = None
    body: str | None = None
    author: str | None = None
    reviewed_at: date | None = None
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Review(BaseModel):
    sku: str
    external_review_id: str
    rating: int
    title: str | None = None
    body: str | None = None
    author: str | None = None
    reviewed_at: date | None = None
    created_at: datetime | None = None
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    sku: str
    name: str
    url: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = "AUD"
    availability: str | None = None
    rating_value: float | None = None
    review_count: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    crawl_run_id: UUID | None = None
    scraped_at: datetime | None = None
    source_type: SourceType = "petbarn_snapshot"
    rating_distribution: dict[str, int] = Field(default_factory=dict)
    sentiment: dict[str, float] = Field(default_factory=dict)
    reviews: list[Review] = Field(default_factory=list)


class Chat(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    next_sequence_no: int = 0


class ChatMessage(BaseModel):
    id: UUID
    chat_id: UUID
    turn_id: UUID
    sequence_no: int
    role: MessageRole
    content: str
    created_at: datetime
    prompt_version: str | None = None


class ToolCall(BaseModel):
    id: UUID
    chat_id: UUID
    turn_id: UUID
    message_id: UUID | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    status: ToolStatus = "running"
    error_type: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latency_ms: int | None = None


class AgentRun(BaseModel):
    id: UUID
    chat_id: UUID
    turn_id: UUID
    status: RunStatus
    user_message_id: UUID
    assistant_message_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    tools_called_count: int = 0
    agent_steps: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    history_tokens: int | None = None
    tool_result_tokens: int | None = None
    system_tools_tokens: int | None = None
    latency_ms: int | None = None
    prompt_version: str | None = None
    model: str | None = None


class Usage(BaseModel):
    history_messages: int = 0
    history_tokens: int = 0
    tool_result_tokens: int = 0
    system_tools_tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    cache_hit_rate: float | None = None
    tools_called: int = 0
    agent_steps: int = 0
    latency_ms: int | None = None
    model: str | None = None
    prompt_version: str | None = None


class AgentResult(BaseModel):
    answer: str
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_context: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


class ReviewExtractionResult(BaseModel):
    reviews: list[ReviewInput] = Field(default_factory=list)
    pages_fetched: int = 0
    truncated: bool = False
