import os
import sys
from datetime import datetime
import httpx
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Configure Page Settings
st.set_page_config(
    page_title="OmniBrain Orchestrator",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Premium CSS Injection
st.markdown(
    """
    <style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap');

    /* Global Fonts & Palette */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        letter-spacing: -0.5px;
    }

    /* Main Container Styles */
    .stApp {
        background: linear-gradient(135deg, #0e1117 0%, #161a24 100%);
        color: #e2e8f0;
    }

    /* Glassmorphism Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 16px;
        padding: 24px;
        border: 1px rgba(255, 255, 255, 0.08) solid;
        backdrop-filter: blur(10px);
        margin-bottom: 20px;
        transition: all 0.3s ease;
    }
    
    .glass-card:hover {
        border-color: rgba(99, 102, 241, 0.4);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        transform: translateY(-2px);
    }

    /* Header styling */
    .main-header {
        font-size: 2.8rem;
        background: linear-gradient(90deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px;
        font-weight: 700;
    }

    .subtitle {
        font-size: 1.1rem;
        color: #94a3b8;
        margin-bottom: 30px;
    }

    /* Status Badges */
    .status-badge {
        padding: 6px 12px;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
    }
    .status-badge-healthy {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-badge-unhealthy {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Sidebar tweaks */
    section[data-testid="stSidebar"] {
        background-color: #0b0d13;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Input adjustments */
    div[data-baseweb="input"] {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%);
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
        transform: scale(1.02);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Centralized Configuration loading
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_PREFIX = os.getenv("API_V1_PREFIX", "/api/v1")
FULL_API_URL = f"{BACKEND_URL}{API_PREFIX}"

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
    st.image(
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=256&auto=format&fit=crop",
        width=80,
    )
    st.markdown("### OmniBrain RAG")
    st.markdown("Agentic Multi-Modal Orchestration")
    st.markdown("---")

    # Navigation menu using radio
    menu_options = [
        "🏠 Home",
        "📊 Dashboard",
        "📤 Upload Documents",
        "🔍 Semantic Search",
        "🗄️ SQL Intelligence",
        "💬 Orchestrator Chat",
        "📈 Observability",
        "⚙️ Settings",
    ]
    selected_option = st.radio("Navigation", menu_options, index=0)

    # Set state based on selection
    if "🏠 Home" in selected_option:
        st.session_state.active_tab = "Home"
    elif "📊 Dashboard" in selected_option:
        st.session_state.active_tab = "Dashboard"
    elif "📤 Upload Documents" in selected_option:
        st.session_state.active_tab = "Upload"
    elif "🔍 Semantic Search" in selected_option:
        st.session_state.active_tab = "Search"
    elif "🗄️ SQL Intelligence" in selected_option:
        st.session_state.active_tab = "SQL"
    elif "💬 Orchestrator Chat" in selected_option:
        st.session_state.active_tab = "Chat"
    elif "📈 Observability" in selected_option:
        st.session_state.active_tab = "Observability"
    elif "⚙️ Settings" in selected_option:
        st.session_state.active_tab = "Settings"

    st.markdown("---")

    # Status Monitor
    st.markdown("#### System Status")
    if st.session_state.api_healthy:
        st.markdown(
            '<div class="status-badge status-badge-healthy">Backend: Operational</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge status-badge-unhealthy">Backend: Disconnected</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.db_healthy:
        st.markdown(
            '<div class="status-badge status-badge-healthy" style="margin-top: 5px;">Database: Healthy</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge status-badge-unhealthy" style="margin-top: 5px;">Database: Offline</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.caption(f"Backend API URL:\n`{FULL_API_URL}`")
    st.caption(f"Environment: `{health_data.get('environment', 'Unknown')}`")


# ==============================================================================
# MAIN PAGE RENDERING
# ==============================================================================

# Page Layout Header
st.markdown('<div class="main-header">OmniBrain</div>', unsafe_allow_html=True)

# 1. HOME PAGE
if st.session_state.active_tab == "Home":
    st.markdown('<div class="subtitle">Agentic Multi-Modal RAG Orchestrator Platform</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>Welcome to OmniBrain!</h3>
            <p>
                OmniBrain is a production-grade enterprise platform designed to orchestrate document intelligence, 
                semantic search, structured SQL reasoning, and multi-agent workflows. 
            </p>
            <p><strong>Core Features Planned:</strong></p>
            <ul>
                <li><strong>Multi-Modal Extraction</strong>: Deep analysis of PDFs containing text, tables, and images.</li>
                <li><strong>Dynamic Multi-Agent System</strong>: Graph-based agent execution powered by LangGraph.</li>
                <li><strong>SQL + Vector Fusion</strong>: Joint semantic and structured database queries with citation tracing.</li>
                <li><strong>Enterprise Safety & Observability</strong>: NeMo Guardrails and Langfuse monitoring.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div class="glass-card">
                <h4>System Configuration Summary</h4>
                <table style="width:100%; font-size: 0.95rem;">
                    <tr><td><strong>FastAPI Endpoint:</strong></td><td><code>http://localhost:8000</code></td></tr>
                    <tr><td><strong>Database Target:</strong></td><td>SQLite (SQLAlchemy Core)</td></tr>
                    <tr><td><strong>Active ORM Models:</strong></td><td>BaseDeclarative</td></tr>
                    <tr><td><strong>Logging Handler:</strong></td><td>Rotating File + Console</td></tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="glass-card">
                <h4>API Integration Status</h4>
                <p>The frontend is communicating dynamically with the FastAPI backend. You can browse API docs at <a href="http://localhost:8000/docs" target="_blank" style="color: #6366f1; text-decoration: none; font-weight:600;">Swagger Docs</a>.</p>
                <p>All startup tasks, including engine binding, CORS policy registration, and file logger rotation, are operational.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

# 2. DASHBOARD
elif st.session_state.active_tab == "Dashboard":
    st.markdown('<div class="subtitle">System Performance & Storage Analytics</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>📊 Analytics Dashboard Placeholder</h3>
            <p>This panel will display vector index metrics, query execution logs, agent token consumptions, and document parsing progress in subsequent modules.</p>
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
    completed_docs = sum(1 for d in documents_list if d.get("status") == "COMPLETED")
    failed_docs = sum(1 for d in documents_list if d.get("status") == "FAILED")

    c1, c2, c3 = st.columns(3)
    c1.metric("Indexed Documents", str(docs_data.get("total", 0)), help="Number of documents uploaded (Qdrant/FAISS + SQLite).")
    c2.metric("Total Vector Nodes", str(total_chunks), help="Count of chunks registered in the active vector store.")
    c3.metric("Completed / Failed", f"{completed_docs} / {failed_docs}", help="Ingestion outcomes across all uploads.")

    if documents_list:
        st.markdown("#### Recent Documents")
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
            use_container_width=True,
        )

# 3. UPLOAD PAGE
elif st.session_state.active_tab == "Upload":
    st.markdown('<div class="subtitle">Ingest Documents for Semantic Retrieval</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>📤 Document Uploader</h3>
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
        st.info(f"{len(uploaded_files)} file(s) ready. Click below to start processing.")

        if st.button("🚀 Process Documents"):
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
                use_container_width=True,
            )

            succeeded = sum(1 for r in summary_rows if r["Status"] == "COMPLETED")
            if succeeded:
                st.success(f"{succeeded}/{len(summary_rows)} document(s) ingested successfully.")
            if succeeded < len(summary_rows):
                st.warning(f"{len(summary_rows) - succeeded} file(s) were rejected or failed. See the message column above.")

            # Module 4: visual content preview for successfully ingested documents
            completed_doc_ids = [r["DocumentID"] for r in summary_rows if r["Status"] == "COMPLETED" and r["DocumentID"]]
            if completed_doc_ids:
                st.markdown("#### 🖼️ Visual Content Preview")
                for doc_id in completed_doc_ids:
                    try:
                        assets_resp = httpx.get(f"{FULL_API_URL}/documents/{doc_id}/assets", timeout=10.0)
                        assets = assets_resp.json().get("assets", []) if assets_resp.status_code == 200 else []
                    except Exception:
                        assets = []

                    if not assets:
                        continue

                    doc_filename = next((r["Filename"] for r in summary_rows if r["DocumentID"] == doc_id), f"doc {doc_id}")
                    with st.expander(f"📄 {doc_filename} — {len(assets)} extracted asset(s)"):
                        for asset in assets:
                            icon = "🖼️" if asset["asset_type"] == "image" else "📊"
                            cols = st.columns([1, 3])
                            with cols[0]:
                                if asset["asset_type"] == "image":
                                    try:
                                        st.image(
                                            f"{FULL_API_URL}/documents/{doc_id}/assets/{asset['id']}/file",
                                            width=140,
                                        )
                                    except Exception:
                                        st.caption("(preview unavailable)")
                                else:
                                    st.markdown(f"{icon} **Table**")
                            with cols[1]:
                                st.caption(f"{icon} Page {asset['page_number']} — {asset['asset_type']}")
                                st.write(asset.get("caption") or "_No description available._")

# 3b. SEMANTIC SEARCH PAGE
elif st.session_state.active_tab == "Search":
    st.markdown('<div class="subtitle">Semantic Retrieval Over Ingested Documents</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>🔍 Semantic Search</h3>
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

    MODALITY_ICONS = {"text": "📝", "image_caption": "🖼️", "table": "📊"}

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
            options=["📝 Text", "🖼️ Images", "📊 Tables"],
        )

    modality_map = {"📝 Text": "text", "🖼️ Images": "image_caption", "📊 Tables": "table"}
    selected_chunk_types = [modality_map[m] for m in modality_labels]

    if st.button("🔎 Search") and query_text.strip():
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
                        st.warning("No matching chunks found. Try uploading documents first or rephrasing your query.")

                    for rank, item in enumerate(search_data["results"], start=1):
                        modality = item.get("chunk_type", "text")
                        icon = MODALITY_ICONS.get(modality, "📝")
                        with st.container():
                            st.markdown(
                                f"""
                                <div class="glass-card">
                                    <p><strong>#{rank}</strong> {icon} <span style="color:#94a3b8;">{modality}</span>
                                    &nbsp; Similarity Score: <strong>{item['similarity_score']:.4f}</strong></p>
                                    <p>{item['content']}</p>
                                    <p style="color:#94a3b8; font-size:0.9rem;">📄 <strong>{item['filename']}</strong> — Page {item['page_number']}, Chunk #{item['chunk_index']}</p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                else:
                    st.error(f"Search failed: HTTP {search_response.status_code} — {search_response.text}")
            except Exception as e:
                st.error(f"Could not reach the backend search API: {e}")

# 3c. SQL INTELLIGENCE PAGE
elif st.session_state.active_tab == "SQL":
    st.markdown('<div class="subtitle">Natural-Language &amp; Raw SQL Access to OmniBrain\'s Structured Data</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>🗄️ SQL Intelligence</h3>
            <p>The SQL Agent translates natural-language questions into read-only SQL over OmniBrain's own
            ingestion database (documents, chunks, extracted assets), validates them, and executes them safely.
            You can also browse the schema or run raw SQL directly below.</p>
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
            f'<div class="status-badge status-badge-healthy">Database: Connected · {len(available_tables)} table(s)</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="status-badge status-badge-unhealthy">Database: Unreachable</div>', unsafe_allow_html=True)

    # --- Schema browser ---
    with st.expander("📋 Schema Browser", expanded=False):
        try:
            schema_resp = httpx.get(f"{FULL_API_URL}/sql/schema", timeout=5.0)
            schema_tables = schema_resp.json().get("tables", []) if schema_resp.status_code == 200 else []
        except Exception:
            schema_tables = []

        for table in schema_tables:
            st.markdown(f"**{table['table_name']}**")
            st.dataframe(
                [
                    {
                        "Column": c["name"],
                        "Type": c["type"],
                        "Nullable": c["nullable"],
                        "Primary Key": c["primary_key"],
                    }
                    for c in table["columns"]
                ],
                use_container_width=True,
            )

    st.markdown("#### 💬 Ask a Question")
    nl_question = st.text_input(
        "Natural-language question", placeholder="e.g. How many documents have been uploaded?"
    )
    if st.button("🧠 Ask SQL Agent") and nl_question.strip():
        with st.spinner("Generating and safely executing SQL..."):
            try:
                nl_response = httpx.post(f"{FULL_API_URL}/sql/query", json={"question": nl_question}, timeout=30.0)
                if nl_response.status_code == 200:
                    nl_data = nl_response.json()
                    st.caption(f"Status: `{nl_data['status']}` — {nl_data['message']}")
                    if nl_data.get("sql"):
                        st.code(nl_data["sql"], language="sql")
                    if nl_data.get("explanation"):
                        st.caption(f"💡 {nl_data['explanation']}")
                    if nl_data.get("rows"):
                        st.markdown("**Query Results**")
                        st.dataframe(nl_data["rows"], use_container_width=True)
                        if nl_data.get("truncated"):
                            st.info(f"Results truncated to the first {len(nl_data['rows'])} row(s).")
                else:
                    st.error(f"SQL query failed: HTTP {nl_response.status_code} — {nl_response.text}")
            except Exception as e:
                st.error(f"Could not reach the backend SQL API: {e}")

    st.markdown("#### ⌨️ Raw SQL Query Interface")
    raw_sql = st.text_area(
        "Read-only SQL statement", placeholder="SELECT status, COUNT(*) AS total FROM documents GROUP BY status"
    )
    if st.button("▶️ Execute SQL") and raw_sql.strip():
        with st.spinner("Validating and executing SQL..."):
            try:
                exec_response = httpx.post(f"{FULL_API_URL}/sql/execute", json={"sql": raw_sql}, timeout=30.0)
                if exec_response.status_code == 200:
                    exec_data = exec_response.json()
                    st.success(exec_data["message"])
                    st.code(exec_data["sql"], language="sql")
                    if exec_data.get("rows"):
                        st.dataframe(exec_data["rows"], use_container_width=True)
                    else:
                        st.info("Query executed successfully but returned no rows.")
                else:
                    error_detail = exec_response.json().get("error", {}).get("message", exec_response.text)
                    st.error(f"SQL execution rejected: {error_detail}")
            except Exception as e:
                st.error(f"Could not reach the backend SQL API: {e}")

# 4. CHAT PAGE
elif st.session_state.active_tab == "Chat":
    st.markdown('<div class="subtitle">Interact with the LangGraph Multi-Agent Team</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>💬 Agentic RAG Chat Interface</h3>
            <p>Converse with the Module 3 LangGraph orchestrator: a Supervisor agent routes your question to the
            Retrieval / Vision / SQL agents, and a Response Synthesizer combines their output into a single
            citation-grounded answer.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    AGENT_ICONS = {
        "supervisor": "🧭",
        "retrieval_agent": "🔍",
        "vision_agent": "🖼️",
        "sql_agent": "🗄️",
        "synthesizer": "🧩",
    }

    def render_execution_trace(trace_steps: list) -> None:
        for step in trace_steps:
            icon = AGENT_ICONS.get(step["agent"], "⚙️")
            status_icon = "✅" if step["status"] == "success" else "⚠️"
            st.caption(
                f"{icon} **{step['agent']}** — {step['action']} {status_icon} "
                f"({step['duration_ms']:.0f} ms) — {step['detail']}"
            )

    CITATION_MODALITY_ICONS = {"text": "📝", "image_caption": "🖼️", "table": "📊", "database": "🗄️"}

    def render_citations(citations: list) -> None:
        if not citations:
            st.caption("No source citations for this response.")
            return
        for c in citations:
            modality = c.get("chunk_type", "text")
            icon = CITATION_MODALITY_ICONS.get(modality, "📝")
            if modality == "database":
                st.markdown(f"- {icon} `{c['filename']}` — _(structured database query result)_")
            else:
                st.markdown(
                    f"- {icon} `{c['filename']}` — **Page {c['page_number']}, Chunk #{c['chunk_index']}** "
                    f"_({modality})_ (Relevance Score: {c['similarity_score']:.2f})"
                )

    # Replay prior turns in this session
    chat_container = st.container()
    with chat_container:
        if not st.session_state.chat_history:
            with st.chat_message("assistant", avatar="🧠"):
                st.markdown(
                    "Welcome to OmniBrain Chat! Ask me questions about your uploaded documents, tables, or images. "
                    "Upload PDFs on the **Upload Documents** page first for grounded answers."
                )

        for turn in st.session_state.chat_history:
            st.chat_message("user").write(turn["query"])
            with st.chat_message("assistant", avatar="🧠"):
                st.markdown(f"**Agent Answer** _(intent: `{turn['intent']}`, agents: {', '.join(turn['agents_invoked'])})_")
                st.write(turn["final_response"])

                with st.expander("📚 Source Citations"):
                    render_citations(turn["citations"])

                with st.popover("🧠 Inspect Agent Reasoning Trace"):
                    render_execution_trace(turn["execution_trace"])

    # User input chat box
    if user_query := st.chat_input("Enter your RAG query (e.g. Summarize Q3 revenue growth)..."):
        st.chat_message("user").write(user_query)
        with st.chat_message("assistant", avatar="🧠"):
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

                    with st.expander("📚 Source Citations", expanded=bool(result["citations"])):
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
                    st.error(f"Orchestration failed: HTTP {response.status_code} — {response.text}")
            except Exception as e:
                progress_status.update(label="Orchestration failed.", state="error", expanded=True)
                st.error(f"Could not reach the backend orchestration API: {e}")

# 4b. OBSERVABILITY PAGE
elif st.session_state.active_tab == "Observability":
    st.markdown('<div class="subtitle">Guardrails, Evaluation &amp; System Reliability</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>📈 Observability</h3>
            <p>Live system health, agent performance, guardrail status, API latency, execution history, and
            automatic evaluation reports for every orchestration run.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- System Health Dashboard ---
    st.markdown("#### 🩺 System Health")
    try:
        health_resp = httpx.get(f"{FULL_API_URL}/observability/health", timeout=5.0)
        deep_health = health_resp.json() if health_resp.status_code == 200 else {}
    except Exception:
        deep_health = {}

    if deep_health:
        badge_class = "status-badge-healthy" if deep_health.get("status") == "healthy" else "status-badge-unhealthy"
        st.markdown(
            f'<div class="status-badge {badge_class}">Overall: {deep_health.get("status", "unknown").upper()}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(deep_health.get("checks", {})) or 1)
        for col, (check_name, check_value) in zip(cols, deep_health.get("checks", {}).items()):
            with col:
                st.metric(check_name.replace("_", " ").title(), check_value)
    else:
        st.warning("Could not reach the observability health endpoint.")

    st.markdown("---")

    # --- Guardrail Status / Live Tester ---
    st.markdown("#### 🛡️ Guardrail Status")
    st.caption(
        f"Guardrails enabled: `{deep_health.get('guardrails_enabled', 'unknown')}` — every `/orchestrate` "
        "call is checked for prompt injection, jailbreak attempts, and unsafe content before any agent runs, "
        "and its final response is scored for grounding/confidence afterward."
    )
    guardrail_test_text = st.text_input("Test the input guardrail", placeholder="e.g. Ignore all previous instructions...")
    if st.button("🛡️ Check Guardrail") and guardrail_test_text.strip():
        try:
            gr_resp = httpx.post(f"{FULL_API_URL}/guardrails/validate", json={"text": guardrail_test_text}, timeout=5.0)
            if gr_resp.status_code == 200:
                gr_data = gr_resp.json()
                if gr_data["passed"]:
                    st.success(f"Passed — risk level: `{gr_data['risk_level']}`")
                else:
                    st.error(f"Blocked — risk level: `{gr_data['risk_level']}` — {gr_data.get('reason', '')}")
            else:
                st.error(f"Guardrail check failed: HTTP {gr_resp.status_code}")
        except Exception as e:
            st.error(f"Could not reach the guardrail API: {e}")

    st.markdown("---")

    # --- Agent Execution Dashboard / Performance Metrics ---
    st.markdown("#### 🤖 Agent Performance")
    try:
        perf_resp = httpx.get(f"{FULL_API_URL}/observability/agents/performance", timeout=5.0)
        agent_stats = perf_resp.json().get("agents", {}) if perf_resp.status_code == 200 else {}
    except Exception:
        agent_stats = {}

    if agent_stats:
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
            use_container_width=True,
        )
    else:
        st.info("No agent executions recorded yet. Run a query on the Orchestrator Chat page first.")

    # --- API Latency Metrics ---
    st.markdown("#### ⚡ API Performance Metrics")
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
    st.markdown("#### 🕒 Execution History")
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
            use_container_width=True,
        )
    else:
        st.info("No execution history recorded yet.")

    st.markdown("---")

    # --- Evaluation Reports ---
    st.markdown("#### 📋 Evaluation Reports")
    try:
        reports_resp = httpx.get(f"{FULL_API_URL}/evaluation/reports?limit=10", timeout=5.0)
        reports = reports_resp.json() if reports_resp.status_code == 200 else []
    except Exception:
        reports = []

    if reports:
        for report in reversed(reports):
            with st.expander(f"🧵 {report['thread_id'][:12]}… — {report['query'][:60]}"):
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
        st.info("No evaluation reports yet. Run a query on the Orchestrator Chat page first.")

# 5. SETTINGS
elif st.session_state.active_tab == "Settings":
    st.markdown('<div class="subtitle">Configure Model Paramerters & Database Schemas</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card">
            <h3>⚙️ Platform Configuration</h3>
            <p>Adjust system configurations and toggle routing paths below.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("settings_form"):
        st.subheader("Model Configs")
        selected_model = st.selectbox("OpenAI LLM Model Choice", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"])
        temperature = st.slider("Temperature", 0.0, 1.0, 0.2, step=0.05)

        st.subheader("Vector Database Connection Settings")
        qdrant_url = st.text_input("Qdrant Endpoint", "http://localhost:6333")

        st.subheader("FastAPI Backend URL config")
        backend_url_input = st.text_input("Backend Base URL", value=BACKEND_URL)

        submit = st.form_submit_button("Save Configurations")
        if submit:
            st.success("Configuration modifications cached locally. Setup persistence in future steps.")
