# Humanitarian Intelligence Backend

Python backend for the Humanitarian Intelligence Platform. It contains the FastAPI
application, ETL pipelines, PostgreSQL migrations, grounded-AI logic, and backend tests.

See the repository-level `README.md` for complete local-development and deployment
instructions.

The read-only MCP server wraps the existing HTTPS API rather than connecting directly to
PostgreSQL. Set `MCP_API_BASE_URL` to a local or deployed API and run `humanitarian-mcp`.
