# Artificial Intelligence Courier Management System

This project is a lightweight Python web application for managing courier operations with an AI-style dispatch assistant.

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

## Free hosting options

Because this is a Python web app, use a free hosting subdomain instead of a static-site host:

- Render: `your-app.onrender.com`
- PythonAnywhere: `your-username.pythonanywhere.com`

## Easiest option: Render

1. Upload this project to GitHub.
2. Create a new Web Service on Render and connect your repo.
3. Use these settings:

```text
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

4. Render will provide a free `onrender.com` subdomain.

This app now reads the deployment port from the `PORT` environment variable, which is required for most hosting platforms.

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
