# Software Engineer Agent

This repository implements a modular AI agent framework designed to automate and assist with software engineering tasks. The agent leverages a collection of tools, memory modules, and prompt templates to perform actions such as code execution, environment inspection, and integration with external services.

## Features

- **Agent Core**: The main agent logic is implemented in `sentient_agent/agent.py`.
- **Memory Service**: Persistent memory support via PostgreSQL, located in `sentient_agent/memory/postgres_memory_service.py`.
- **Prompt Management**: Customizable prompt templates in `sentient_agent/prompts/prompts.py`.
- **Tooling**: Extensible toolset including shell command execution and environment information, found in `sentient_agent/tools/`.
- **Source Collection**: Utility for collecting source code in `collect_source.py`.
- **Main Entry Point**: The main script to run the agent is `main.py`.

## Directory Structure

- `sentient_agent/` - Core agent logic, memory, prompts, and tools
- `output/` - Generated output and logs (ignored by git)
- `collect_source.py` - Source code collection utility
- `main.py` - Main entry point

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   Or use `pyproject.toml` with Poetry or pip:
   ```bash
   pip install .
   ```
2. **Configure environment variables** as needed (e.g., for database connections).

## Usage

Run the main agent:

```bash
python main.py
```

## Development

- All Python bytecode, build artifacts, and the `output/` directory are git-ignored.
- Extend the agent by adding new tools in `sentient_agent/tools/` or new memory modules in `sentient_agent/memory/`.

## License

Specify your license here.

## Tech Stack

This project is built using the **Google Agent Development Kit** as its primary framework, along with:

- Python 3.12+
- PostgreSQL (for memory persistence)
- Modular, extensible architecture for agent tools and prompts
