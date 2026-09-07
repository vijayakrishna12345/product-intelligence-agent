"""Shared Streamlit resource handles. One cache for every page."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from pia.agent.factory import create_catalog_agent
from pia.db import create_client
from pia.domain.errors import LLMError
from pia.repositories.agent_runs import AgentRunRepository
from pia.repositories.catalog import CatalogRepository
from pia.repositories.chats import ChatRepository
from pia.services.agent_runner import AgentRunner
from pia.services.catalog import CatalogService
from pia.services.comparison import ComparisonService
from pia.settings import get_settings


@st.cache_resource
def _executor() -> ThreadPoolExecutor:
    settings = get_settings()
    return ThreadPoolExecutor(max_workers=settings.agent_worker_max_workers)


@st.cache_resource
def get_stores() -> tuple:
    settings = get_settings()
    client = create_client(settings)
    chats = ChatRepository(client)
    runs = AgentRunRepository(client)
    catalog_repo = CatalogRepository(client, settings=settings)
    catalog = CatalogService(catalog_repo, settings)
    comparison = ComparisonService(catalog, settings)
    try:
        agent = create_catalog_agent(catalog, comparison, settings)
    except LLMError:
        agent = None
    runner = None
    if agent is not None:
        runner = AgentRunner(chats, runs, agent, catalog, _executor(), settings)
    return chats, runs, catalog, runner
