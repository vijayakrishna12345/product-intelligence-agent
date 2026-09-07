"""Streamlit Community Cloud entrypoint."""

import streamlit as st

from pia.logging import configure_logging
from pia.settings import get_settings
from pia.ui.about import render_about
from pia.ui.catalog_page import render_catalog
from pia.ui.chat import render_chat
from pia.ui.usage_page import render_usage

configure_logging(get_settings().log_level)
st.set_page_config(page_title="Product Intelligence Agent", layout="wide")
page = st.navigation(
    {
        "Assistant": [
            st.Page(render_chat, title="Chat", icon="💬", url_path="chat"),
        ],
        "Catalog": [
            st.Page(render_catalog, title="Crawled catalog", icon="📦", url_path="catalog"),
        ],
        "Observability": [
            st.Page(
                render_usage,
                title="Context & usage",
                icon="📊",
                url_path="usage",
            ),
        ],
        "Help": [
            st.Page(render_about, title="About", icon="ℹ️", url_path="about"),
        ],
    }
)
page.run()
