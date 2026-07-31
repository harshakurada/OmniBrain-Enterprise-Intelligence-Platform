import os
import sys
from datetime import datetime
import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Configure Page Settings
st.set_page_config(
    page_title="OmniBrain Orchestrator",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# DESIGN SYSTEM -- a dark, single-accent "console" theme: Inter + JetBrains
# Mono, real Material Symbols icons (same icon set used by native Streamlit
# `icon=":material/x:"` params, loaded here as a webfont so custom HTML can
# use it too), restrained shadows, no gradient text, no rainbow chip salad.
# ==============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0..1,0');

    .material-symbols-rounded {
        font-family: 'Material Symbols Rounded';
        font-weight: normal;
        font-style: normal;
        font-size: 20px;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        vertical-align: -4px;
    }

    /* ---------------------------------------------------------------- */
    /* Design tokens                                                     */
    /* ---------------------------------------------------------------- */
    :root {
        --ob-bg-0: #0a0b0d;
        --ob-bg-1: #0d0f12;
        --ob-surface: #14171b;
        --ob-surface-strong: #1a1e23;
        --ob-border: #23272d;
        --ob-border-strong: #343a41;
        --ob-text-primary: #e8eaed;
        --ob-text-secondary: #9aa1a9;
        --ob-text-muted: #656c73;
        --ob-accent-1: #2f81f7;
        --ob-accent-2: #2f81f7;
        --ob-accent-3: #2f81f7;
        --ob-accent-soft: rgba(47, 129, 247, 0.12);
        --ob-success: #3fb950;
        --ob-success-soft: rgba(63, 185, 80, 0.12);
        --ob-danger: #f85149;
        --ob-danger-soft: rgba(248, 81, 73, 0.12);
        --ob-warning: #d29922;
        --ob-warning-soft: rgba(210, 153, 34, 0.12);
        --ob-info: #58a6ff;
        --ob-radius-lg: 10px;
        --ob-radius-md: 8px;
        --ob-radius-sm: 6px;
        --ob-shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.3);
        --ob-shadow-strong: 0 12px 32px rgba(0, 0, 0, 0.4);
    }

    /* ---------------------------------------------------------------- */
    /* Global type & surface                                             */
    /* ---------------------------------------------------------------- */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    code, pre, .stCode, .stCodeBlock, .stMarkdown code {
        font-family: 'JetBrains Mono', monospace !important;
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        letter-spacing: -0.015em;
        color: var(--ob-text-primary);
    }

    .stApp {
        background:
            radial-gradient(ellipse 900px 500px at 20% -10%, rgba(47, 129, 247, 0.06), transparent 60%),
            var(--ob-bg-0);
        color: var(--ob-text-primary);
    }

    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--ob-border-strong); border-radius: 8px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--ob-accent-1); }

    @keyframes obFadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .glass-card, div[data-testid="stMetric"] {
        animation: obFadeIn 0.25s ease both;
    }

    /* ---------------------------------------------------------------- */
    /* Cards                                                              */
    /* ---------------------------------------------------------------- */
    .glass-card {
        background: var(--ob-surface);
        border-radius: var(--ob-radius-lg);
        padding: 24px 26px;
        border: 1px solid var(--ob-border);
        box-shadow: var(--ob-shadow-soft);
        margin-bottom: 20px;
        transition: border-color 0.15s ease;
    }
    .glass-card:hover { border-color: var(--ob-border-strong); }
    .glass-card h3, .glass-card h4 { margin-top: 0; display: flex; align-items: center; gap: 10px; }
    .glass-card p { color: var(--ob-text-secondary); line-height: 1.65; }
    .card-icon { color: var(--ob-accent-1); font-size: 22px !important; }

    .feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin-top: 16px; }
    .feature-tile {
        background: var(--ob-surface-strong);
        border: 1px solid var(--ob-border);
        border-radius: var(--ob-radius-md);
        padding: 18px 20px;
        transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .feature-tile:hover { border-color: var(--ob-accent-1); transform: translateY(-2px); }
    .feature-tile .icon {
        width: 34px; height: 34px; border-radius: 8px; margin-bottom: 12px;
        display: flex; align-items: center; justify-content: center;
        background: var(--ob-accent-soft); color: var(--ob-accent-1);
    }
    .feature-tile .icon .material-symbols-rounded { font-size: 19px; vertical-align: 0; }
    .feature-tile .title { font-weight: 600; color: var(--ob-text-primary); margin-bottom: 4px; font-size: 0.95rem; }
    .feature-tile .desc { color: var(--ob-text-secondary); font-size: 0.85rem; line-height: 1.5; }

    /* ---------------------------------------------------------------- */
    /* Header / hero                                                     */
    /* ---------------------------------------------------------------- */
    .main-header {
        font-size: 1.9rem;
        color: var(--ob-text-primary);
        margin-bottom: 2px;
        font-weight: 800;
        letter-spacing: -0.02em;
        display: inline-block;
    }
    .subtitle {
        font-size: 0.96rem;
        color: var(--ob-text-secondary);
        margin-bottom: 24px;
        font-weight: 400;
    }

    /* ---------------------------------------------------------------- */
    /* Badges & tags                                                      */
    /* ---------------------------------------------------------------- */
    .status-badge {
        padding: 5px 12px 5px 10px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        letter-spacing: 0.01em;
    }
    .status-badge-healthy { background: var(--ob-success-soft); color: var(--ob-success); }
    .status-badge-unhealthy { background: var(--ob-danger-soft); color: var(--ob-danger); }
    .status-badge-warning { background: var(--ob-warning-soft); color: var(--ob-warning); }
    .status-badge-info { background: var(--ob-accent-soft); color: var(--ob-info); }
    .status-badge .material-symbols-rounded { font-size: 15px; vertical-align: -2px; }

    .tag {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 3px 9px; border-radius: 6px; font-size: 0.76rem; font-weight: 600;
        background: var(--ob-surface-strong); border: 1px solid var(--ob-border); color: var(--ob-text-secondary);
    }
    .tag .material-symbols-rounded { font-size: 14px; vertical-align: -2px; color: var(--ob-accent-1); }

    /* ---------------------------------------------------------------- */
    /* Sidebar                                                            */
    /* ---------------------------------------------------------------- */
    section[data-testid="stSidebar"] {
        background: var(--ob-bg-1);
        border-right: 1px solid var(--ob-border);
    }
    section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

    .brand-lockup { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
    .brand-mark {
        width: 36px; height: 36px; border-radius: 9px; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        font-weight: 800; font-size: 0.85rem;
        background: var(--ob-accent-1); color: #fff;
    }
    .brand-name { font-weight: 700; font-size: 1.05rem; color: var(--ob-text-primary); line-height: 1.2; }
    .brand-tag { font-size: 0.74rem; color: var(--ob-text-muted); }

    /* Sidebar nav buttons: full-width, left-aligned, flat. Uses real
       st.button widgets (not a styled radio group), so there is no custom
       DOM restructuring that could ever break click handling. */
    section[data-testid="stSidebar"] .stButton { margin-bottom: 1px; }
    section[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        justify-content: flex-start;
        text-align: left;
        font-weight: 500;
        font-size: 0.88rem;
        padding: 8px 12px;
        border-radius: var(--ob-radius-sm);
    }
    section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background: transparent;
        border: 1px solid transparent;
        color: var(--ob-text-secondary);
        box-shadow: none;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background: var(--ob-surface-strong);
        color: var(--ob-text-primary);
        border-color: transparent;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: var(--ob-accent-soft);
        color: var(--ob-accent-1);
        border: 1px solid transparent;
        box-shadow: none;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] .stButton > button:focus:not(:active) {
        box-shadow: none;
    }

    /* ---------------------------------------------------------------- */
    /* Inputs                                                            */
    /* ---------------------------------------------------------------- */
    div[data-baseweb="input"], div[data-baseweb="select"] > div, .stTextArea textarea, div[data-baseweb="base-input"] {
        background-color: var(--ob-surface-strong) !important;
        border-radius: var(--ob-radius-sm) !important;
        border: 1px solid var(--ob-border) !important;
    }
    div[data-baseweb="input"]:focus-within, .stTextArea textarea:focus {
        border-color: var(--ob-accent-1) !important;
        box-shadow: 0 0 0 3px var(--ob-accent-soft) !important;
    }

    /* ---------------------------------------------------------------- */
    /* Buttons (main content area)                                       */
    /* ---------------------------------------------------------------- */
    .stButton > button {
        border-radius: var(--ob-radius-sm);
        font-weight: 600;
        font-size: 0.88rem;
        transition: filter 0.12s ease, transform 0.06s ease;
    }
    div[data-testid="stMainBlockContainer"] .stButton > button[kind="primary"] {
        background: var(--ob-accent-1);
        border: 1px solid var(--ob-accent-1);
        box-shadow: var(--ob-shadow-soft);
    }
    .stButton > button:hover { filter: brightness(1.1); }
    .stButton > button:active { transform: translateY(1px); }

    /* ---------------------------------------------------------------- */
    /* Page header + live status tag                                     */
    /* ---------------------------------------------------------------- */
    .header-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
    .live-pulse {
        display: inline-flex; align-items: center; gap: 8px; font-size: 0.8rem; font-weight: 600;
        color: var(--ob-text-secondary); padding: 7px 14px; border-radius: 9999px;
        border: 1px solid var(--ob-border); background: var(--ob-surface);
    }
    .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ob-success); position: relative; }
    .live-dot::after {
        content: ''; position: absolute; inset: -4px; border-radius: 50%;
        border: 1px solid var(--ob-success); opacity: 0.5; animation: obRing 2.2s ease-out infinite;
    }
    .live-dot.down { background: var(--ob-danger); }
    .live-dot.down::after { border-color: var(--ob-danger); animation: none; opacity: 0; }
    @keyframes obRing {
        0% { transform: scale(0.6); opacity: 0.6; }
        100% { transform: scale(1.8); opacity: 0; }
    }

    /* ---------------------------------------------------------------- */
    /* Config rows (key/value display)                                   */
    /* ---------------------------------------------------------------- */
    .config-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--ob-border); font-size: 0.88rem; gap: 12px; }
    .config-row:last-child { border-bottom: none; }
    .config-row .label { color: var(--ob-text-secondary); }
    .config-row .value { color: var(--ob-text-primary); font-weight: 600; text-align: right; }
    .config-row .value code { background: var(--ob-surface-strong); padding: 2px 8px; border-radius: 5px; font-size: 0.82em; }

    /* ---------------------------------------------------------------- */
    /* Agent trace tags (Orchestrator Chat)                              */
    /* ---------------------------------------------------------------- */
    .agent-chip {
        display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px 3px 8px; border-radius: 6px;
        font-size: 0.78rem; font-weight: 600; margin-right: 6px;
        background: var(--ob-surface-strong); color: var(--ob-text-primary); border: 1px solid var(--ob-border);
    }
    .agent-chip .material-symbols-rounded { font-size: 14px; vertical-align: -2px; }
    .agent-chip-supervisor .material-symbols-rounded { color: #58a6ff; }
    .agent-chip-retrieval_agent .material-symbols-rounded { color: #79c0ff; }
    .agent-chip-vision_agent .material-symbols-rounded { color: #d2a8ff; }
    .agent-chip-sql_agent .material-symbols-rounded { color: #ffa657; }
    .agent-chip-synthesizer .material-symbols-rounded { color: #7ee787; }
    .agent-chip-default .material-symbols-rounded { color: var(--ob-text-muted); }

    /* ---------------------------------------------------------------- */
    /* Native widget polish                                              */
    /* ---------------------------------------------------------------- */
    div[data-testid="stMetric"] {
        background: var(--ob-surface);
        border: 1px solid var(--ob-border);
        border-radius: var(--ob-radius-md);
        padding: 14px 18px;
    }
    div[data-testid="stMetricLabel"] { color: var(--ob-text-secondary); font-size: 0.8rem; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }

    div[data-testid="stDataFrame"] {
        border-radius: var(--ob-radius-md);
        overflow: hidden;
        border: 1px solid var(--ob-border);
    }

    div[data-testid="stExpander"] {
        border: 1px solid var(--ob-border) !important;
        border-radius: var(--ob-radius-md) !important;
        background: var(--ob-surface);
    }

    div[data-testid="stChatMessage"] {
        background: var(--ob-surface);
        border: 1px solid var(--ob-border);
        border-radius: var(--ob-radius-md);
        padding: 4px 6px;
    }

    div[data-testid="stAlert"] { border-radius: var(--ob-radius-md); border: 1px solid var(--ob-border); }

    div[data-testid="stFileUploaderDropzone"] {
        background: var(--ob-surface-strong);
        border: 1px dashed var(--ob-border-strong);
        border-radius: var(--ob-radius-md);
    }

    hr { border-color: var(--ob-border) !important; margin: 1.4rem 0 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def icon_span(name: str, size: int = 18, color: str = "inherit") -> str:
    """Renders a Material Symbols Rounded glyph inline inside raw HTML
    (the same icon set used by native `st.button(icon=":material/x:")`
    calls, exposed here for the custom HTML cards/tags that native
    Streamlit params can't reach).
    """
    return (
        f'<span class="material-symbols-rounded" '
        f'style="font-size:{size}px; color:{color};">{name}</span>'
    )


# Centralized Configuration loading
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_PREFIX = os.getenv("API_V1_PREFIX", "/api/v1")
FULL_API_URL = f"{BACKEND_URL}{API_PREFIX}"
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Initialize Session State
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.active_tab = "Home"
    st.session_state.chat_history = []
    st.session_state.orchestrator_thread_id = None
    st.session_state.uploaded_files = []
    st.session_state.db_healthy = False
    st.session_state.api_healthy = False


# Helper: Check Backend Health
def check_backend_health() -> dict:
    try:
        response = httpx.get(f"{FULL_API_URL}/health", timeout=3.0)
        if response.status_code == 200:
            data = response.json()
            st.session_state.api_healthy = data.get("status") == "healthy"
            st.session_state.db_healthy = data.get("database", {}).get("status") == "healthy"
            return data
    except Exception:
        st.session_state.api_healthy = False
        st.session_state.db_healthy = False
    return {}


# Auto check health
health_data = check_backend_health()

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
            <div class="brand-mark">OB</div>
            <div>
                <div class="brand-name">OmniBrain</div>
                <div class="brand-tag">Multi-Agent RAG Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Navigation -- real st.button widgets (icon + label), not a styled
    # radio group. Each button sets active_tab directly and reruns, so
    # there is no fragile DOM-hacking involved in highlighting the
    # current page.
    NAV_ITEMS = [
        ("Home", "home", "Home"),
        ("Dashboard", "monitoring", "Dashboard"),
        ("Upload", "upload_file", "Upload Documents"),
        ("Search", "search", "Semantic Search"),
        ("SQL", "database", "SQL Intelligence"),
        ("Chat", "forum", "Orchestrator Chat"),
        ("Observability", "insights", "Observability"),
        ("Settings", "tune", "Settings"),
    ]
    for tab_key, icon_name, label in NAV_ITEMS:
        if st.button(
            label,
            key=f"nav_{tab_key}",
            icon=f":material/{icon_name}:",
            width="stretch",
            type="primary" if st.session_state.active_tab == tab_key else "secondary",
        ):
            st.session_state.active_tab = tab_key
            st.rerun()

    st.markdown("---")

    # Status Monitor
    st.markdown("##### System Status")
    if st.session_state.api_healthy:
        st.markdown(
            f'<div class="status-badge status-badge-healthy">{icon_span("check_circle", 15)} Backend Operational</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="status-badge status-badge-unhealthy">{icon_span("error", 15)} Backend Disconnected</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.db_healthy:
        st.markdown(
            f'<div class="status-badge status-badge-healthy" style="margin-top: 6px;">{icon_span("check_circle", 15)} Database Healthy</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="status-badge status-badge-unhealthy" style="margin-top: 6px;">{icon_span("error", 15)} Database Offline</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.caption(f"Backend API URL:\n`{FULL_API_URL}`")
    st.caption(f"Environment: `{health_data.get('environment', 'Unknown')}`")
    st.caption(f"OmniBrain v{APP_VERSION}")


# ==============================================================================
# MAIN PAGE RENDERING
# ==============================================================================

# Page Layout Header
_overall_up = st.session_state.api_healthy and st.session_state.db_healthy
_dot_class = "" if _overall_up else "down"
if not st.session_state.api_healthy:
    _status_text = "Backend disconnected"
elif not st.session_state.db_healthy:
    _status_text = "Database offline"
else:
    _status_text = "All systems operational"

st.markdown(
    f"""
    <div class="header-row">
        <div class="main-header">OmniBrain</div>
        <div class="live-pulse"><span class="live-dot {_dot_class}"></span>{_status_text}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 1. HOME PAGE
if st.session_state.active_tab == "Home":
    st.markdown('<div class="subtitle">Agentic multi-modal RAG orchestrator platform</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("waving_hand", 22, "var(--ob-accent-1)")} Welcome to OmniBrain</h3>
            <p>
                A production-grade, multi-agent Retrieval-Augmented Generation platform. A LangGraph-orchestrated
                Supervisor routes every question to specialized Retrieval, Vision, and SQL agents, synthesizes a
                single citation-grounded answer, and validates it through a built-in guardrails and evaluation layer.
            </p>
            <div class="feature-grid">
                <div class="feature-tile">
                    <div class="icon">{icon_span("description", 19)}</div>
                    <div class="title">Multi-Modal Extraction</div>
                    <div class="desc">Text, tables, and images parsed from every uploaded PDF and made independently searchable.</div>
                </div>
                <div class="feature-tile">
                    <div class="icon">{icon_span("hub", 19)}</div>
                    <div class="title">Multi-Agent Orchestration</div>
                    <div class="desc">A LangGraph Supervisor routes each query to the right combination of agents in parallel.</div>
                </div>
                <div class="feature-tile">
                    <div class="icon">{icon_span("database", 19)}</div>
                    <div class="title">SQL + Vector Fusion</div>
                    <div class="desc">Natural-language Text-to-SQL and semantic search combined with full citation tracing.</div>
                </div>
                <div class="feature-tile">
                    <div class="icon">{icon_span("image_search", 19)}</div>
                    <div class="title">Vision Intelligence</div>
                    <div class="desc">Charts, diagrams, and screenshots analyzed and indexed alongside document text.</div>
                </div>
                <div class="feature-tile">
                    <div class="icon">{icon_span("shield", 19)}</div>
                    <div class="title">Guardrails</div>
                    <div class="desc">Prompt-injection and jailbreak detection on input; grounding/confidence scoring on output.</div>
                </div>
                <div class="feature-tile">
                    <div class="icon">{icon_span("monitoring", 19)}</div>
                    <div class="title">Observability</div>
                    <div class="desc">Request tracing, per-agent performance metrics, and automatic evaluation reports.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        db_status_label = "Healthy" if st.session_state.db_healthy else "Unavailable"
        st.markdown(
            f"""
            <div class="glass-card">
                <h4>{icon_span("settings", 19, "var(--ob-accent-1)")} System Configuration</h4>
                <div class="config-row"><span class="label">Backend Endpoint</span><span class="value"><code>{FULL_API_URL}</code></span></div>
                <div class="config-row"><span class="label">Database</span><span class="value">SQLite &middot; {db_status_label}</span></div>
                <div class="config-row"><span class="label">Vector Backend</span><span class="value">Qdrant (auto-fallback to local FAISS)</span></div>
                <div class="config-row"><span class="label">Environment</span><span class="value">{health_data.get('environment', 'Unknown')}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        api_status_label = "Connected" if st.session_state.api_healthy else "Disconnected"
        st.markdown(
            f"""
            <div class="glass-card">
                <h4>{icon_span("api", 19, "var(--ob-accent-1)")} API Integration Status</h4>
                <p>Backend status: <strong>{api_status_label}</strong>. Explore every endpoint interactively via
                <a href="{BACKEND_URL}/docs" target="_blank" style="color: var(--ob-accent-1); text-decoration: none; font-weight:600;">Swagger Docs</a>.</p>
                <p>Startup validation, structured logging, and graceful shutdown are all active for this session (v{APP_VERSION}).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

# 2. DASHBOARD
elif st.session_state.active_tab == "Dashboard":
    st.markdown('<div class="subtitle">System performance and storage analytics</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("monitoring", 22, "var(--ob-accent-1)")} Ingestion Analytics</h3>
            <p>Live counts pulled directly from the Documents API -- every number below reflects the current
            state of your SQLite metadata store and active vector backend.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Live metrics pulled from the Documents API
    try:
        docs_response = httpx.get(f"{FULL_API_URL}/documents", timeout=5.0)
        docs_data = docs_response.json() if docs_response.status_code == 200 else {"total": 0, "documents": []}
    except Exception:
        docs_data = {"total": 0, "documents": []}

    documents_list = docs_data.get("documents", [])
    total_chunks = sum(d.get("chunk_count", 0) for d in documents_list)
    total_images = sum(d.get("image_count", 0) for d in documents_list)
    total_tables = sum(d.get("table_count", 0) for d in documents_list)
    completed_docs = sum(1 for d in documents_list if d.get("status") == "COMPLETED")
    failed_docs = sum(1 for d in documents_list if d.get("status") == "FAILED")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Indexed Documents", str(docs_data.get("total", 0)), help="Number of documents uploaded (Qdrant/FAISS + SQLite).")
    c2.metric("Total Chunks", str(total_chunks), help="Count of embedded chunks (text, image captions, tables) in the active vector store.")
    c3.metric("Images / Tables", f"{total_images} / {total_tables}", help="Visual assets extracted across all documents.")
    c4.metric("Completed / Failed", f"{completed_docs} / {failed_docs}", help="Ingestion outcomes across all uploads.")

    if documents_list:
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("###### Documents by status")
            status_counts = pd.Series([d.get("status", "UNKNOWN") for d in documents_list]).value_counts()
            st.bar_chart(status_counts, color="#2f81f7", horizontal=True, height=200)
        with chart_col2:
            st.markdown("###### Content composition")
            composition = pd.DataFrame(
                {"count": [total_chunks, total_images, total_tables]},
                index=["Text Chunks", "Images", "Tables"],
            )
            st.bar_chart(composition, color="#3fb950", horizontal=True, height=200)

        st.markdown("###### Recent Documents")
        st.dataframe(
            [
                {
                    "Filename": d["filename"],
                    "Status": d["status"],
                    "Pages": d["page_count"],
                    "Chunks": d["chunk_count"],
                }
                for d in documents_list[:10]
            ],
            width="stretch",
        )
    else:
        st.info("No documents ingested yet. Head to **Upload Documents** to get started.", icon=":material/upload_file:")

# 3. UPLOAD PAGE
elif st.session_state.active_tab == "Upload":
    st.markdown('<div class="subtitle">Ingest documents for semantic retrieval</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("upload_file", 22, "var(--ob-accent-1)")} Document Uploader</h3>
            <p>Upload PDF documents to run them through the ingestion pipeline: text extraction, recursive chunking, OpenAI embeddings, and vector indexing (Qdrant, or local FAISS if Qdrant is unavailable).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Choose PDF file(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) ready. Click below to start processing.", icon=":material/info:")

        if st.button("Process Documents", type="primary", icon=":material/rocket_launch:"):
            progress_bar = st.progress(0.0)
            status_placeholder = st.empty()
            summary_rows = []

            for i, uploaded_file in enumerate(uploaded_files):
                status_placeholder.markdown(f"Processing **`{uploaded_file.name}`** ({i + 1}/{len(uploaded_files)})...")
                try:
                    response = httpx.post(
                        f"{FULL_API_URL}/documents/upload",
                        files=[("files", (uploaded_file.name, uploaded_file.getvalue(), "application/pdf"))],
                        timeout=120.0,
                    )
                    if response.status_code == 200:
                        result = response.json()["results"][0]
                        summary_rows.append(
                            {
                                "Filename": result["filename"],
                                "Status": result["status"],
                                "Pages": result.get("page_count") or "-",
                                "Chunks": result.get("chunk_count") or "-",
                                "Message": result.get("message") or "",
                                "DocumentID": result.get("document_id"),
                            }
                        )
                    else:
                        summary_rows.append(
                            {
                                "Filename": uploaded_file.name,
                                "Status": "ERROR",
                                "Pages": "-",
                                "Chunks": "-",
                                "Message": f"HTTP {response.status_code}",
                                "DocumentID": None,
                            }
                        )
                except Exception as e:
                    summary_rows.append(
                        {
                            "Filename": uploaded_file.name,
                            "Status": "ERROR",
                            "Pages": "-",
                            "Chunks": "-",
                            "Message": str(e),
                            "DocumentID": None,
                        }
                    )

                progress_bar.progress((i + 1) / len(uploaded_files))

            status_placeholder.markdown("**Processing complete.**")
            st.dataframe(
                [{k: v for k, v in r.items() if k != "DocumentID"} for r in summary_rows],
                width="stretch",
            )

            succeeded = sum(1 for r in summary_rows if r["Status"] == "COMPLETED")
            if succeeded:
                st.success(f"{succeeded}/{len(summary_rows)} document(s) ingested successfully.", icon=":material/check_circle:")
            if succeeded < len(summary_rows):
                st.warning(f"{len(summary_rows) - succeeded} file(s) were rejected or failed. See the message column above.", icon=":material/warning:")

            # Module 4: visual content preview for successfully ingested documents
            completed_doc_ids = [r["DocumentID"] for r in summary_rows if r["Status"] == "COMPLETED" and r["DocumentID"]]
            if completed_doc_ids:
                st.markdown("###### Visual Content Preview")
                for doc_id in completed_doc_ids:
                    try:
                        assets_resp = httpx.get(f"{FULL_API_URL}/documents/{doc_id}/assets", timeout=10.0)
                        assets = assets_resp.json().get("assets", []) if assets_resp.status_code == 200 else []
                    except Exception:
                        assets = []

                    if not assets:
                        continue

                    doc_filename = next((r["Filename"] for r in summary_rows if r["DocumentID"] == doc_id), f"doc {doc_id}")
                    with st.expander(f"{doc_filename} — {len(assets)} extracted asset(s)", icon=":material/folder_open:"):
                        for asset in assets:
                            is_image = asset["asset_type"] == "image"
                            cols = st.columns([1, 3])
                            with cols[0]:
                                if is_image:
                                    try:
                                        st.image(
                                            f"{FULL_API_URL}/documents/{doc_id}/assets/{asset['id']}/file",
                                            width=140,
                                        )
                                    except Exception:
                                        st.caption("(preview unavailable)")
                                else:
                                    st.markdown(f"{icon_span('table_chart', 20)} **Table**", unsafe_allow_html=True)
                            with cols[1]:
                                asset_icon = icon_span("image", 14) if is_image else icon_span("table_chart", 14)
                                st.markdown(
                                    f'<span style="color:var(--ob-text-muted); font-size:0.85rem;">{asset_icon} '
                                    f'Page {asset["page_number"]} — {asset["asset_type"]}</span>',
                                    unsafe_allow_html=True,
                                )
                                st.write(asset.get("caption") or "_No description available._")

# 3b. SEMANTIC SEARCH PAGE
elif st.session_state.active_tab == "Search":
    st.markdown('<div class="subtitle">Semantic retrieval over ingested documents</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("search", 22, "var(--ob-accent-1)")} Semantic Search</h3>
            <p>Search across every ingested PDF using OpenAI embeddings and vector similarity. Results span both
            text and visual content (image descriptions, tables) by default -- multi-modal retrieval -- and include
            the source filename, page number, and a relevance score for citation.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Populate an optional per-document filter from currently ingested documents
    try:
        docs_resp = httpx.get(f"{FULL_API_URL}/documents", timeout=5.0)
        available_docs = docs_resp.json().get("documents", []) if docs_resp.status_code == 200 else []
    except Exception:
        available_docs = []

    doc_options = {"All documents": None}
    doc_options.update({f"{d['filename']} (id={d['id']})": d["id"] for d in available_docs})

    MODALITY_ICONS = {"text": "description", "image_caption": "image", "table": "table_chart"}

    col_q, col_k = st.columns([3, 1])
    with col_q:
        query_text = st.text_input("Search query", placeholder="e.g. What was the revenue growth in Q3?")
    with col_k:
        top_k = st.slider("Top K", min_value=1, max_value=20, value=5)

    col_doc, col_modality = st.columns([2, 2])
    with col_doc:
        doc_filter_label = st.selectbox("Restrict to document", list(doc_options.keys()))
    with col_modality:
        modality_labels = st.multiselect(
            "Content types (leave empty for all -- multi-modal)",
            options=["Text", "Images", "Tables"],
        )

    modality_map = {"Text": "text", "Images": "image_caption", "Tables": "table"}
    selected_chunk_types = [modality_map[m] for m in modality_labels]

    if st.button("Search", type="primary", icon=":material/search:") and query_text.strip():
        with st.spinner("Embedding query and searching the vector index..."):
            try:
                payload = {"query": query_text, "top_k": top_k}
                document_id = doc_options[doc_filter_label]
                if document_id is not None:
                    payload["document_id"] = document_id
                if selected_chunk_types:
                    payload["chunk_types"] = selected_chunk_types

                search_response = httpx.post(f"{FULL_API_URL}/search", json=payload, timeout=30.0)

                if search_response.status_code == 200:
                    search_data = search_response.json()
                    st.caption(f"Vector backend: `{search_data['vector_backend']}` · {search_data['total_results']} result(s)")

                    if not search_data["results"]:
                        st.warning("No matching chunks found. Try uploading documents first or rephrasing your query.", icon=":material/search_off:")

                    SNIPPET_WORD_LIMIT = 45

                    def _make_snippet(content: str, query: str, word_limit: int = SNIPPET_WORD_LIMIT):
                        """Returns (snippet, was_truncated). Caps at an exact word
                        count (not characters, which only approximates word count)
                        and centers the window on the first query-term match so the
                        snippet is actually relevant to what was asked, instead of
                        always showing the start of an arbitrary chunk.
                        """
                        words = content.split()
                        if len(words) <= word_limit:
                            return content, False

                        query_terms = {w.lower().strip(".,?!:;\"'()") for w in query.split() if len(w) > 3}
                        match_idx = next(
                            (i for i, w in enumerate(words) if w.lower().strip(".,?!:;\"'()") in query_terms),
                            None,
                        )
                        start = 0 if match_idx is None else max(0, match_idx - word_limit // 3)
                        end = min(len(words), start + word_limit)
                        start = max(0, end - word_limit)

                        prefix = "…" if start > 0 else ""
                        suffix = "…" if end < len(words) else ""
                        return f"{prefix}{' '.join(words[start:end])}{suffix}", True

                    for rank, item in enumerate(search_data["results"], start=1):
                        modality = item.get("chunk_type", "text")
                        icon_name = MODALITY_ICONS.get(modality, "description")
                        content = item["content"]
                        snippet, is_long = _make_snippet(content, query_text)
                        with st.container():
                            st.markdown(
                                f"""
                                <div class="glass-card">
                                    <p><strong>#{rank}</strong> &nbsp;<span class="tag">{icon_span(icon_name, 14)} {modality}</span>
                                    &nbsp; Similarity Score: <strong>{item['similarity_score']:.4f}</strong></p>
                                    <p>{snippet}</p>
                                    <p style="color:var(--ob-text-secondary); font-size:0.85rem;">{icon_span('description', 14)} <strong>{item['filename']}</strong> — Page {item['page_number']}, Chunk #{item['chunk_index']}</p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            if is_long:
                                with st.expander("Show full excerpt"):
                                    st.write(content)
                else:
                    st.error(f"Search failed: HTTP {search_response.status_code} — {search_response.text}", icon=":material/error:")
            except Exception as e:
                st.error(f"Could not reach the backend search API: {e}", icon=":material/error:")

# 3c. SQL INTELLIGENCE PAGE
elif st.session_state.active_tab == "SQL":
    st.markdown('<div class="subtitle">Ask questions about your data — no SQL knowledge needed</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("database", 22, "var(--ob-accent-1)")} SQL Intelligence</h3>
            <p>Type a question in plain English below (e.g. "How many documents have I uploaded?") and the AI
            works out the right database query, runs it safely, and shows you the answer. You never need to
            write SQL yourself — that's handled behind the scenes.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Database connection/status ---
    try:
        tables_resp = httpx.get(f"{FULL_API_URL}/sql/tables", timeout=5.0)
        sql_connected = tables_resp.status_code == 200
        available_tables = tables_resp.json().get("tables", []) if sql_connected else []
    except Exception:
        sql_connected = False
        available_tables = []

    if sql_connected:
        st.markdown(
            f'<div class="status-badge status-badge-healthy">{icon_span("check_circle", 15)} Ready — {len(available_tables)} data table(s) available</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="status-badge status-badge-unhealthy">{icon_span("error", 15)} Not connected — try again shortly</div>',
            unsafe_allow_html=True,
        )

    with st.expander("What data can I ask about? (optional)", expanded=False, icon=":material/menu_book:"):
        st.caption("A quick reference of what's available — like a table of contents for your data. You don't need to read this to ask questions.")
        try:
            schema_resp = httpx.get(f"{FULL_API_URL}/sql/schema", timeout=5.0)
            schema_tables = schema_resp.json().get("tables", []) if schema_resp.status_code == 200 else []
        except Exception:
            schema_tables = []

        for table in schema_tables:
            st.markdown(f"**{table['table_name']}**")
            st.dataframe(
                [{"Column": c["name"], "Type": c["type"]} for c in table["columns"]],
                width="stretch",
            )

    st.markdown("###### Ask a Question")
    st.caption("Try one of these, or type your own question below:")

    EXAMPLE_QUESTIONS = [
        "How many documents have been uploaded?",
        "Which documents failed to process?",
        "How many images and tables were extracted?",
    ]
    if "sql_nl_question" not in st.session_state:
        st.session_state.sql_nl_question = ""
    chip_cols = st.columns(len(EXAMPLE_QUESTIONS))
    for col, example in zip(chip_cols, EXAMPLE_QUESTIONS):
        if col.button(example, key=f"sql_example_{example}", width="stretch", icon=":material/bolt:"):
            st.session_state.sql_nl_question = example

    nl_question = st.text_input(
        "Your question",
        key="sql_nl_question",
        placeholder="e.g. How many documents have been uploaded?",
        label_visibility="collapsed",
    )
    if st.button("Get Answer", type="primary", icon=":material/smart_toy:") and nl_question.strip():
        with st.spinner("Thinking..."):
            try:
                nl_response = httpx.post(f"{FULL_API_URL}/sql/query", json={"question": nl_question}, timeout=30.0)
                if nl_response.status_code == 200:
                    nl_data = nl_response.json()
                    if nl_data.get("rows"):
                        st.markdown("**Answer**")
                        st.dataframe(nl_data["rows"], width="stretch")
                        if nl_data.get("truncated"):
                            st.caption(f"Showing the first {len(nl_data['rows'])} row(s).")
                    else:
                        st.info(nl_data.get("message") or "No matching data found for that question.", icon=":material/info:")
                    if nl_data.get("explanation"):
                        st.caption(nl_data["explanation"])
                    if nl_data.get("sql"):
                        with st.expander("See the exact database query that was run (optional)", icon=":material/code:"):
                            st.code(nl_data["sql"], language="sql")
                else:
                    st.error(f"Something went wrong: HTTP {nl_response.status_code} — {nl_response.text}", icon=":material/error:")
            except Exception as e:
                st.error(f"Could not reach the backend: {e}", icon=":material/error:")

    with st.expander("Advanced: write raw SQL yourself (optional — only if you already know SQL)", icon=":material/terminal:"):
        st.caption("Most people don't need this — the question box above already does this for you automatically.")
        raw_sql = st.text_area(
            "Read-only SQL statement", placeholder="SELECT status, COUNT(*) AS total FROM documents GROUP BY status"
        )
        if st.button("Execute SQL", icon=":material/play_arrow:") and raw_sql.strip():
            with st.spinner("Validating and executing SQL..."):
                try:
                    exec_response = httpx.post(f"{FULL_API_URL}/sql/execute", json={"sql": raw_sql}, timeout=30.0)
                    if exec_response.status_code == 200:
                        exec_data = exec_response.json()
                        st.success(exec_data["message"], icon=":material/check_circle:")
                        st.code(exec_data["sql"], language="sql")
                        if exec_data.get("rows"):
                            st.dataframe(exec_data["rows"], width="stretch")
                        else:
                            st.info("Query executed successfully but returned no rows.", icon=":material/info:")
                    else:
                        error_detail = exec_response.json().get("error", {}).get("message", exec_response.text)
                        st.error(f"SQL execution rejected: {error_detail}", icon=":material/block:")
                except Exception as e:
                    st.error(f"Could not reach the backend SQL API: {e}", icon=":material/error:")

# 4. CHAT PAGE
elif st.session_state.active_tab == "Chat":
    st.markdown('<div class="subtitle">Interact with the LangGraph multi-agent team</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("forum", 22, "var(--ob-accent-1)")} Agentic RAG Chat Interface</h3>
            <p>Converse with the LangGraph orchestrator: a Supervisor agent routes your question to the
            Retrieval / Vision / SQL agents, and a Response Synthesizer combines their output into a single
            citation-grounded answer.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    AGENT_ICONS = {
        "supervisor": "hub",
        "retrieval_agent": "search",
        "vision_agent": "image_search",
        "sql_agent": "database",
        "synthesizer": "auto_awesome",
    }

    AGENT_CHIP_CLASS = {
        "supervisor": "agent-chip-supervisor",
        "retrieval_agent": "agent-chip-retrieval_agent",
        "vision_agent": "agent-chip-vision_agent",
        "sql_agent": "agent-chip-sql_agent",
        "synthesizer": "agent-chip-synthesizer",
    }

    def render_execution_trace(trace_steps: list) -> None:
        for step in trace_steps:
            icon_name = AGENT_ICONS.get(step["agent"], "settings")
            chip_class = AGENT_CHIP_CLASS.get(step["agent"], "agent-chip-default")
            status_icon = icon_span("check_circle", 14, "var(--ob-success)") if step["status"] == "success" else icon_span("warning", 14, "var(--ob-warning)")
            st.markdown(
                f'<div style="margin:6px 0; font-size:0.85rem; color:var(--ob-text-secondary);">'
                f'<span class="agent-chip {chip_class}">{icon_span(icon_name, 14)} {step["agent"]}</span>'
                f'{step["action"]} {status_icon} '
                f'<span style="color:var(--ob-text-muted);">({step["duration_ms"]:.0f} ms)</span> — {step["detail"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

    CITATION_MODALITY_ICONS = {"text": "description", "image_caption": "image", "table": "table_chart", "database": "database"}

    def render_citations(citations: list) -> None:
        if not citations:
            st.caption("No source citations for this response.")
            return
        for c in citations:
            modality = c.get("chunk_type", "text")
            icon_name = CITATION_MODALITY_ICONS.get(modality, "description")
            if modality == "database":
                st.markdown(f"{icon_span(icon_name, 14)} `{c['filename']}` — _(structured database query result)_", unsafe_allow_html=True)
            else:
                st.markdown(
                    f"{icon_span(icon_name, 14)} `{c['filename']}` — **Page {c['page_number']}, Chunk #{c['chunk_index']}** "
                    f"_({modality})_ (Relevance Score: {c['similarity_score']:.2f})",
                    unsafe_allow_html=True,
                )

    # Replay prior turns in this session
    chat_container = st.container()
    with chat_container:
        if not st.session_state.chat_history:
            with st.chat_message("assistant", avatar=":material/smart_toy:"):
                st.markdown(
                    "Welcome to OmniBrain Chat! Ask me questions about your uploaded documents, tables, or images. "
                    "Upload PDFs on the **Upload Documents** page first for grounded answers."
                )

        for turn in st.session_state.chat_history:
            st.chat_message("user").write(turn["query"])
            with st.chat_message("assistant", avatar=":material/smart_toy:"):
                st.markdown(f"**Agent Answer** _(intent: `{turn['intent']}`, agents: {', '.join(turn['agents_invoked'])})_")
                st.write(turn["final_response"])

                with st.expander("Source Citations", icon=":material/link:"):
                    render_citations(turn["citations"])

                with st.popover("Inspect Agent Reasoning Trace", icon=":material/travel_explore:"):
                    render_execution_trace(turn["execution_trace"])

    # User input chat box
    if user_query := st.chat_input("Enter your RAG query (e.g. Summarize Q3 revenue growth)..."):
        st.chat_message("user").write(user_query)
        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            progress_status = st.status("Running multi-agent orchestration...", expanded=True)
            try:
                payload = {"query": user_query, "top_k": 5}
                if st.session_state.orchestrator_thread_id:
                    payload["thread_id"] = st.session_state.orchestrator_thread_id

                response = httpx.post(f"{FULL_API_URL}/orchestrate", json=payload, timeout=60.0)

                if response.status_code == 200:
                    result = response.json()
                    st.session_state.orchestrator_thread_id = result["thread_id"]

                    with progress_status:
                        st.write(f"Supervisor classified intent as **{result['intent']}**.")
                        st.write(f"Agents invoked: **{', '.join(result['agents_invoked'])}**")
                        render_execution_trace(result["execution_trace"])
                    progress_status.update(label="Orchestration complete.", state="complete", expanded=False)

                    st.markdown(
                        f"**Agent Answer** _(intent: `{result['intent']}`, agents: {', '.join(result['agents_invoked'])})_"
                    )
                    st.write(result["final_response"])

                    with st.expander("Source Citations", expanded=bool(result["citations"]), icon=":material/link:"):
                        render_citations(result["citations"])

                    st.session_state.chat_history.append(
                        {
                            "query": user_query,
                            "final_response": result["final_response"],
                            "intent": result["intent"],
                            "agents_invoked": result["agents_invoked"],
                            "citations": result["citations"],
                            "execution_trace": result["execution_trace"],
                        }
                    )
                else:
                    progress_status.update(label="Orchestration failed.", state="error", expanded=True)
                    st.error(f"Orchestration failed: HTTP {response.status_code} — {response.text}", icon=":material/error:")
            except Exception as e:
                progress_status.update(label="Orchestration failed.", state="error", expanded=True)
                st.error(f"Could not reach the backend orchestration API: {e}", icon=":material/error:")

# 4b. OBSERVABILITY PAGE
elif st.session_state.active_tab == "Observability":
    st.markdown('<div class="subtitle">Guardrails, evaluation, and system reliability</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("insights", 22, "var(--ob-accent-1)")} Observability</h3>
            <p>Live system health, agent performance, guardrail status, API latency, execution history, and
            automatic evaluation reports for every orchestration run.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- System Health Dashboard ---
    st.markdown(f"###### {icon_span('favorite', 16, 'var(--ob-accent-1)')} System Health", unsafe_allow_html=True)
    try:
        health_resp = httpx.get(f"{FULL_API_URL}/observability/health", timeout=5.0)
        deep_health = health_resp.json() if health_resp.status_code == 200 else {}
    except Exception:
        deep_health = {}

    if deep_health:
        badge_class = "status-badge-healthy" if deep_health.get("status") == "healthy" else "status-badge-unhealthy"
        badge_icon = "check_circle" if deep_health.get("status") == "healthy" else "error"
        st.markdown(
            f'<div class="status-badge {badge_class}">{icon_span(badge_icon, 15)} Overall: {deep_health.get("status", "unknown").upper()}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(deep_health.get("checks", {})) or 1)
        for col, (check_name, check_value) in zip(cols, deep_health.get("checks", {}).items()):
            with col:
                st.metric(check_name.replace("_", " ").title(), check_value)
    else:
        st.warning("Could not reach the observability health endpoint.", icon=":material/cloud_off:")

    st.markdown("---")

    # --- Guardrail Status / Live Tester ---
    st.markdown(f"###### {icon_span('shield', 16, 'var(--ob-accent-1)')} Guardrail Status", unsafe_allow_html=True)
    st.caption(
        f"Guardrails enabled: `{deep_health.get('guardrails_enabled', 'unknown')}` — every `/orchestrate` "
        "call is checked for prompt injection, jailbreak attempts, and unsafe content before any agent runs, "
        "and its final response is scored for grounding/confidence afterward."
    )
    guardrail_test_text = st.text_input("Test the input guardrail", placeholder="e.g. Ignore all previous instructions...")
    if st.button("Check Guardrail", icon=":material/shield:") and guardrail_test_text.strip():
        try:
            gr_resp = httpx.post(f"{FULL_API_URL}/guardrails/validate", json={"text": guardrail_test_text}, timeout=5.0)
            if gr_resp.status_code == 200:
                gr_data = gr_resp.json()
                if gr_data["passed"]:
                    st.success(f"Passed — risk level: `{gr_data['risk_level']}`", icon=":material/check_circle:")
                else:
                    st.error(f"Blocked — risk level: `{gr_data['risk_level']}` — {gr_data.get('reason', '')}", icon=":material/block:")
            else:
                st.error(f"Guardrail check failed: HTTP {gr_resp.status_code}", icon=":material/error:")
        except Exception as e:
            st.error(f"Could not reach the guardrail API: {e}", icon=":material/error:")

    st.markdown("---")

    # --- Agent Execution Dashboard / Performance Metrics ---
    st.markdown(f"###### {icon_span('smart_toy', 16, 'var(--ob-accent-1)')} Agent Performance", unsafe_allow_html=True)
    try:
        perf_resp = httpx.get(f"{FULL_API_URL}/observability/agents/performance", timeout=5.0)
        agent_stats = perf_resp.json().get("agents", {}) if perf_resp.status_code == 200 else {}
    except Exception:
        agent_stats = {}

    if agent_stats:
        perf_col1, perf_col2 = st.columns([2, 1])
        with perf_col1:
            st.dataframe(
                [
                    {
                        "Agent": agent,
                        "Invocations": stats["invocations"],
                        "Avg Duration (ms)": stats["avg_duration_ms"],
                        "Success Rate": f"{stats['success_rate'] * 100:.0f}%",
                    }
                    for agent, stats in agent_stats.items()
                ],
                width="stretch",
            )
        with perf_col2:
            duration_series = pd.Series({agent: stats["avg_duration_ms"] for agent, stats in agent_stats.items()})
            st.bar_chart(duration_series, color="#2f81f7", horizontal=True, height=180)
    else:
        st.info("No agent executions recorded yet. Run a query on the Orchestrator Chat page first.", icon=":material/info:")

    # --- API Latency Metrics ---
    st.markdown(f"###### {icon_span('bolt', 16, 'var(--ob-accent-1)')} API Performance Metrics", unsafe_allow_html=True)
    try:
        api_metrics_resp = httpx.get(f"{FULL_API_URL}/observability/metrics", timeout=5.0)
        api_metrics = api_metrics_resp.json() if api_metrics_resp.status_code == 200 else {}
    except Exception:
        api_metrics = {}

    if api_metrics:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Requests", api_metrics.get("total_requests", 0))
        c2.metric("Avg Latency", f"{api_metrics.get('avg_latency_ms', 0):.1f} ms")
        c3.metric("P95 Latency", f"{api_metrics.get('p95_latency_ms', 0):.1f} ms")
        c4.metric("Error Rate", f"{api_metrics.get('error_rate', 0) * 100:.1f}%")

    st.markdown("---")

    # --- Execution History ---
    st.markdown(f"###### {icon_span('history', 16, 'var(--ob-accent-1)')} Execution History", unsafe_allow_html=True)
    try:
        history_resp = httpx.get(f"{FULL_API_URL}/observability/execution-history?limit=20", timeout=5.0)
        exec_history = history_resp.json().get("history", []) if history_resp.status_code == 200 else []
    except Exception:
        exec_history = []

    if exec_history:
        st.dataframe(
            [
                {
                    "Timestamp": h["timestamp"],
                    "Agent": h["agent"],
                    "Action": h["action"],
                    "Status": h["status"],
                    "Duration (ms)": h["duration_ms"],
                }
                for h in reversed(exec_history)
            ],
            width="stretch",
        )
    else:
        st.info("No execution history recorded yet.", icon=":material/info:")

    st.markdown("---")

    # --- Evaluation Reports ---
    st.markdown(f"###### {icon_span('fact_check', 16, 'var(--ob-accent-1)')} Evaluation Reports", unsafe_allow_html=True)
    try:
        reports_resp = httpx.get(f"{FULL_API_URL}/evaluation/reports?limit=10", timeout=5.0)
        reports = reports_resp.json() if reports_resp.status_code == 200 else []
    except Exception:
        reports = []

    if reports:
        for report in reversed(reports):
            with st.expander(f"{report['thread_id'][:12]}… — {report['query'][:60]}", icon=":material/description:"):
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Grounded", "Yes" if report["grounded"] else "No")
                col_b.metric("Confidence", f"{report['confidence']:.2f}")
                col_c.metric("Total Duration", f"{report['total_duration_ms']:.0f} ms")
                st.caption(f"Intent: `{report['intent']}` · Agents: {', '.join(report['agents_invoked']) or 'none'}")
                if report.get("retrieval_quality"):
                    rq = report["retrieval_quality"]
                    st.caption(
                        f"Retrieval quality: {rq['result_count']} result(s), avg score {rq['avg_similarity_score']:.2f}"
                    )
                st.json(report["agent_durations_ms"])
    else:
        st.info("No evaluation reports yet. Run a query on the Orchestrator Chat page first.", icon=":material/info:")

# 5. SETTINGS
elif st.session_state.active_tab == "Settings":
    st.markdown('<div class="subtitle">Configuration reference</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>{icon_span("tune", 22, "var(--ob-accent-1)")} Platform Configuration</h3>
            <p>All configuration is sourced from the backend's <code>.env</code> file (see <code>.env.example</code>
            for the full reference). This page reflects the values currently in effect -- to change them, edit
            <code>.env</code> and restart the backend.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("settings_form"):
        st.subheader("Model Configuration")
        st.selectbox("OpenAI LLM Model", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"], help="Set via OPENAI_MODEL in .env")
        st.slider("Synthesizer Temperature", 0.0, 1.0, 0.2, step=0.05, disabled=True, help="Fixed at 0.2 in ResponseSynthesizer")

        st.subheader("Vector Database")
        st.text_input("Qdrant Endpoint", "http://localhost:6333", help="Set via QDRANT_HOST/QDRANT_PORT in .env")

        st.subheader("Backend Connection")
        st.text_input("Backend Base URL", value=BACKEND_URL, help="Set via BACKEND_URL in .env")

        submitted = st.form_submit_button("Save (reference only)")
        if submitted:
            st.info(
                "This panel is a read-only reference, by design -- runtime settings live in `.env` and are "
                "validated at backend startup (see the Observability page for live health/config status).",
                icon=":material/info:",
            )
