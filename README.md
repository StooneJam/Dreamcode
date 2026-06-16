# Dreamcode — AI Competitive Analysis Platform

Dreamcode is a multi-agent platform for automated competitive analysis. Give it a
target product name and an analysis brief, and a pipeline of cooperating LLM agents
collects competitor information from the web, runs sentiment analysis on user
reviews, builds a side-by-side comparison, and produces a professional PDF report.

The pipeline is orchestrated with **LangGraph** and served over **FastAPI** with a
single-page web UI and live SSE streaming of every agent step.

### Highlights

- **Four-agent pipeline** — PM plans → Collector searches the web → Insight analyzes
  sentiment → Reporter writes the report, fully orchestrated by LangGraph.
- **Cross-model debate** — planning and final review bring in LLMs from different
  vendors to challenge each other and reduce single-model bias.
- **Human-in-the-loop** — the run pauses after collection/insight so you can submit
  free-text revisions; the PM re-plans automatically.
- **Runtime key injection** — each run uses the caller's own API keys, passed
  thread-safely via `contextvars`; the server stores no credentials.
- **Professional PDF output** — SWOT, dimension-competitiveness radar, App Store
  rating dual-axis charts, pricing comparison, and review-topic summaries.

---

## Getting Started

### Dependencies

- **Python 3.11+**
- **Node.js 18+** — only needed for the optional App Store review scraper
  (`scripts/node`)
- A system toolchain for [WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)
  on Linux/macOS (Pango, cairo, etc.). On Windows the report renderer falls back to
  ReportLab, so WeasyPrint's native libraries are not required.
- API keys for the LLM and search providers you intend to use:
  - OpenAI-compatible endpoint (PM / Reporter)
  - DeepSeek (Collector / Insight)
  - Doubao / Volcengine Ark (debate judge / final review)
  - [Tavily](https://app.tavily.com) search API (required)

All Python libraries are declared in `pyproject.toml`. There are no hidden runtime
dependencies — a clean `pip install` reproduces the full environment.

### Installing

```bash
git clone https://github.com/StooneJam/Dreamcode.git
cd Dreamcode

# Install the package and its runtime dependencies
pip install -e .

# Optional: development tooling (ruff, pytest, pre-commit)
pip install -e ".[dev]"

# Configure environment variables
cp .env.example .env        # then edit .env and fill in your keys

# Optional: App Store scraper (Node.js)
cd scripts/node && npm install && cd ../..
```

Minimum `.env` keys (also injectable per-run from the web UI):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5

DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com

DOUBAO_API_KEY=...
DOUBAO_MODEL=ep-...
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

TAVILY_API_KEY=tvly-...
```

### Executing the program

**Run the web server (recommended):**

```bash
python scripts/run_server.py            # serves http://localhost:8000
python scripts/run_server.py --port 8080
```

Open the URL in a browser, fill in the target product and analysis brief, supply
the API keys, and watch the agents stream their progress. The finished PDF report
is displayed on the right when the run completes.

**Run offline (no server) via the Python API:**

```python
from cca.graph import build_graph, empty_state
from cca.llm.factory import LLMCredential, use_credentials
from cca.tools.search import use_tavily_key

graph = build_graph(checkpointer=None)
state = empty_state(
    user_query="Compare Feishu's video-meeting features and pricing against DingTalk and Slack",
    target_product="Feishu",
)

creds = {
    "gpt-5":    LLMCredential(api_key="sk-...", model="gpt-5"),
    "deepseek": LLMCredential(api_key="sk-...", model="deepseek-v4-pro",
                              base_url="https://api.deepseek.com"),
}

with use_credentials(creds), use_tavily_key("tvly-..."):
    result = graph.invoke(state)

print(result["report_pdf_path"])
```

**Other entry points:**

```bash
python scripts/demo/dry_run.py          # full pipeline dry-run using .env keys
python scripts/run_report_agent.py      # run only the Reporter on existing profiles
pytest                                  # run the test suite (no real API calls)
```

---

## Project Structure

```
Dreamcode/
├── app/                       # Web layer
│   ├── server.py              # FastAPI entrypoint (endpoints + SSE streaming)
│   ├── index.html             # Single-page front end
│   └── static/                # CSS / JS
├── src/cca/                   # Core Python package
│   ├── agents/                # PM / Collector / Insight / Reporter + Q&A
│   ├── tools/                 # search, charts, PDF rendering, App Store, etc.
│   ├── skills/                # reusable skills (debate, reroute, questionnaire)
│   ├── llm/                   # LLM client factory + runtime key injection
│   ├── prompts/               # agent system prompts (Markdown)
│   ├── auth/                  # SMS OTP authentication
│   ├── store/                 # SQLite persistence for reports and Q&A
│   ├── memory/                # ReAct result cache
│   ├── observability/         # tracing / audit helpers
│   ├── graph.py               # LangGraph orchestration graph
│   ├── schema.py              # Pydantic domain models
│   └── state.py               # LangGraph shared state (TypedDict)
├── scripts/                   # Dev / runner scripts
│   ├── run_server.py          # launch the FastAPI server
│   ├── run_report_agent.py    # run the Reporter standalone
│   ├── demo/                  # offline dry-run / demo runners
│   └── node/                  # Node.js App Store review scraper
├── tests/                     # pytest unit tests (use a FakeLLM, never real APIs)
├── docs/                      # architecture docs / decision records
├── config/config.yaml         # model pricing / task parameters
└── data/                      # runtime data (uploads, cache, memory, examples)
```

---

## Acknowledgements

- [LangGraph](https://github.com/langchain-ai/langgraph) — multi-agent orchestration
- [FastAPI](https://fastapi.tiangolo.com) — async web framework
- [Tavily](https://tavily.com) — search API built for AI agents
- [DeepSeek](https://deepseek.com) / [OpenAI](https://openai.com) / [Doubao](https://www.volcengine.com/product/doubao)

**Team**: StooneJam · BAbykiller322

Issues and suggestions are welcome at [GitHub Issues](https://github.com/StooneJam/Dreamcode/issues).
