# Azure deployment

## Target architecture

```text
Browser
  -> Azure Static Web Apps (React)
  -> Azure Container Apps (FastAPI, scale 0-1)
  -> Azure Database for PostgreSQL Flexible Server
  -> OpenAI API
```

Use the Static Web Apps Free plan and the Container Apps Consumption plan. Use a small
Burstable PostgreSQL server without high availability for this portfolio deployment. The
database is the main recurring cost; stop it when the demo is not needed.

## Required Azure settings

The API container requires these environment variables:

- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, and `DATABASE_USER`
- `DATABASE_PASSWORD`: supplied from Azure Key Vault through a Container Apps secret reference
- `OPENAI_API_KEY`: stored as a Container Apps secret
- `AI_GENERATION_KEY`: protects the POST generation endpoint in public deployments
- `OPENAI_MODEL=gpt-6-luna`
- `API_HOST=0.0.0.0`
- `API_PORT=8000`
- `CORS_ORIGINS`: the final Static Web Apps URL

The frontend build requires:

- `VITE_API_BASE_URL`: the HTTPS URL of the Container App
- `VITE_ENABLE_AI_GENERATION=false`: hides paid generation controls from the public site

Never put production credentials in `.env.example`, GitHub, a Docker image, or a frontend
environment variable.

## Deployment order

1. Sign in with the Azure CLI and select the intended subscription.
2. Create a resource group in the selected Azure region.
3. Create the PostgreSQL Flexible Server and database.
4. From `backend/`, run `humanitarian-etl init-db`, `world-bank`, `unicef`, and `validate`
   against Azure.
5. Build `backend/Dockerfile` with `backend/` as its build context and deploy it to Azure
   Container Apps with external ingress on port 8000.
6. Add `DATABASE_URL` and `OPENAI_API_KEY` as Container Apps secrets.
7. Create the Static Web App from the GitHub repository's `frontend/` directory.
8. Set `VITE_API_BASE_URL` during the frontend build and set the resulting site URL in
   `CORS_ORIGINS` on the Container App.
9. Verify `/health`, the dashboard, a saved brief, and one regeneration request.

## Cost controls

- Set the Container App minimum replicas to zero and maximum replicas to one.
- Use the Static Web Apps Free plan.
- Do not enable PostgreSQL high availability for the portfolio demo.
- Create an Azure budget alert before generating traffic.
- Stop PostgreSQL when the demo is not in use. Azure automatically starts a stopped Flexible
  Server after seven days, so delete the resource group when the public demo is no longer needed.
