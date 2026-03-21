# Kapruka Gift-Concierge Agent

A pure Python AI agent for kapruka.com that provides personalised gift recommendations.

## Setup

### 1. Install Python dependencies and Playwright browser
```bash
pip install -r requirements.txt && playwright install chromium
```

### 2. Start Qdrant vector database
```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 3. Configure environment
```bash
cp .env.example .env
# Open .env and fill in your ANTHROPIC_API_KEY
```

### 4. Scrape the Kapruka product catalog
```bash
python phase1/scraper.py
```

### 5. Ingest catalog into Qdrant
```bash
python phase1/ingest.py
```

### 6. Start the API server
```bash
uvicorn api.main:app --reload
```

### 7. Start the frontend
```bash
cd frontend && npm install && npm run dev
```

## Project Structure

```
kapruka-concierge/
├── phase1/          # Scraper and ingestion scripts
├── memory/          # Recipient profile and vector memory management
├── agents/          # Core agent logic (pure Python, no frameworks)
├── api/             # FastAPI backend
├── frontend/        # UI (A2UI Protocol renderer)
├── tests/           # Test suite
├── recipient_profiles.json
└── requirements.txt
```

## Architecture

- **No orchestration frameworks** — zero LangGraph, CrewAI, or AutoGen
- **Transport**: A2UI Protocol over SSE (JSONL stream)
- **Vector DB**: Qdrant for semantic product search
- **LLM**: Anthropic Claude via direct API calls
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2
