# FastCode REST API — reference stub

Interactive **OpenAPI** and **Swagger UI** are served by the running API process:

- URL pattern: `http://<host>:<port>/docs`
- Default **port** when running `python api.py` locally: **8000**
- **Dockerfile** / `docker compose` publish the API on host port **8001** (`api.py --port 8001` inside the container)

## e-Bridge optional authentication

If the `ebridge_auth` package is available in the environment, `api.py` may attach Keycloak-based dependencies to selected routes. If that import fails, the service starts without enterprise auth. Consult the parent e-Bridge workspace for Keycloak and token configuration.

## Discovering routes

Use `/docs` or `/openapi.json` on a live instance — do not duplicate endpoint lists here (they drift). Major functional areas include repository load/index, query, health, and upload helpers; exact paths and models are defined in `api.py`.
