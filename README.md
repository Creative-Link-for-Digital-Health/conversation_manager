# Conversation Research System - Setup Guide

## 📦 Conda Environment Setup

### Prerequisites
- [Anaconda](https://www.anaconda.com/products/distribution) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html) installed
- Git (for cloning the repository)

### Quick Start

```bash
# Create the conda environment
conda env create -f environment.yml

# Activate the environment
conda activate conversation-manager


## 🚀 System Setup

### 1. Configuration Files

Create your configuration files:

```bash
# Copy and customize scenario configuration
cp scenario.toml.template scenario.toml

# Copy and add your API secrets (DO NOT COMMIT THIS FILE!)
cp .secrets.toml.template .secrets.toml
```

### 2. Configure Your Research Scenario

Edit `scenario.toml`:
- Set your scenario name and description
- Configure LLM provider settings
- Set system prompt UUID (after creating prompts)
- Enable/configure RAG if needed
- Enable/configure REDCap logging if needed

### 3. Add API Keys

Edit `.secrets.toml` with your actual API keys:
- LLM Provider API key
- REDCap API token (if using REDCap)
- Any other provider API keys

### 4. Create Prompts and Document Collections

```bash
# Start the prompt management interface
streamlit run prompt_tracker.py
```

- Create your system prompts

```bash
# Start the document management interface
streamlit run document_tracker.py
```
- Set up document collections for RAG
- Upload research documents

### 5. Start the Backend

```bash
# Start the Flask backend
python app.py
```

The backend will:
- ✅ Validate configuration
- ✅ Initialize prompt management
- ✅ Set up RAG system (if enabled)
- ✅ Connect to REDCap (if enabled)
- 🚀 Start API server on http://localhost:8000

### 6. Test the System

```bash
# Test API health
curl http://localhost:8000/health

# Test configuration
curl http://localhost:8000/config

# Test REDCap (if enabled)
curl http://localhost:8000/redcap/test
```

## 📁 Project Structure

TODO: Rewrite this!!!!

```
conversation-research/
├── environment.yml              # Conda environment
├── app.py                       # Flask backend
├── prompt_tracker.py           # Streamlit interface
├── scenario.toml               # Research scenario config
├── .secrets.toml              # API keys (DO NOT COMMIT)
├── vector_search.py           # RAG/document processing
├── redcap_logger.py          # REDCap integration
├── prompt_utils.py           # Prompt management
├── prompts.db               # Prompt database
├── chroma_db/              # Vector database (auto-created)
├── documents/             # Document collections
└── conversation_logs/     # Local conversation logs
```


## 📚 Additional Resources

- [Conda User Guide](https://docs.conda.io/projects/conda/en/latest/user-guide/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [REDCap API Documentation](https://redcap.vanderbilt.edu/api/help/)
- [PyCap Documentation](https://redcap-tools.github.io/PyCap/)
- [Docling Documentation](https://github.com/DS4SD/docling)