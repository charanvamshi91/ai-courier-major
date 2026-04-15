# Artificial Intelligence Courier Management System

This project is a lightweight Python web application for managing courier operations with an AI-style dispatch assistant.

## Live Demo

Deployed on Render:

```text
https://ai-courier-major.onrender.com
```

## Demo Notice

The current public Render deployment is still a demo environment until a Neon Postgres `DATABASE_URL` is added in Render. Without that variable, the app falls back to local SQLite storage and courier/shipment data may reset after redeploys, service restarts, or platform filesystem cleanup.

## Features

- Courier registration and fleet utilization tracking
- Shipment creation with priority, distance, and package weight
- AI recommendation engine for courier assignment
- Shipment status updates from dispatch to delivery
- SQLite storage with seeded demo data
- JSON API endpoint at `/api/recommendations`

## Run the project

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Deployment

This project is deployed on Render using the included `render.yaml` blueprint and is now prepared for Neon Postgres.

Render configuration:

```text
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

Environment variables:

```text
DATABASE_URL=<your Neon connection string>
PYTHON_VERSION=3.11.4
```

The app reads the deployment port from the `PORT` environment variable, binds to a public host for Render, and uses Neon Postgres automatically whenever `DATABASE_URL` is present.

## Neon Setup

1. Create a Postgres project in Neon.
2. Copy the connection string from Neon.
3. In Render, open your web service settings and add `DATABASE_URL`.
4. Redeploy the service.
5. After redeploy, the app will use persistent Postgres storage instead of temporary SQLite demo data.

## Tech stack

- Python 3.11
- SQLite for local fallback
- Neon Postgres for persistent live deployment
- Built-in `http.server`
- HTML and CSS dashboard UI

## AI scoring logic

The recommendation engine ranks available couriers by:

- vehicle suitability
- remaining capacity
- shipment priority
- estimated route pressure from distance and weight

It is heuristic-based, which makes it easy to understand and present in an academic or mini-project setting without requiring external machine learning libraries.
