# Artificial Intelligence Courier Management System

This project is a lightweight Python web application for managing courier operations with an AI-style dispatch assistant.

## Live Demo

Deployed on Render:

```text
https://ai-courier-major.onrender.com
```

## Demo Notice

The public Render deployment is a demo environment. It uses temporary hosted storage with the local SQLite file, so courier and shipment data may reset after redeploys, service restarts, or platform filesystem cleanup.

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

This project is currently deployed on Render using the included `render.yaml` blueprint.

Render configuration:

```text
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

The app reads the deployment port from the `PORT` environment variable and binds to a public host for compatibility with hosting platforms like Render.

Because the current deployment uses SQLite on Render's ephemeral filesystem, it should be treated as a demonstration build rather than permanent production storage.

## Tech stack

- Python 3.11
- SQLite
- Built-in `http.server`
- HTML and CSS dashboard UI

## AI scoring logic

The recommendation engine ranks available couriers by:

- vehicle suitability
- remaining capacity
- shipment priority
- estimated route pressure from distance and weight

It is heuristic-based, which makes it easy to understand and present in an academic or mini-project setting without requiring external machine learning libraries.
