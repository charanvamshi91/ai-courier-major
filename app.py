import json
import os
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "courier_ai.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

COURIER_SEED = [
    ("Riya Express", "Kolkata Hub", "Bike", "Available", 12, 4),
    ("Arjun Logistics", "Delhi Hub", "Van", "Available", 40, 18),
    ("Meera Fleet", "Mumbai Hub", "Truck", "On Route", 120, 85),
    ("Kabir Courier", "Bengaluru Hub", "Bike", "Available", 10, 3),
]

SHIPMENT_SEED = [
    (
        "AICMS-1001",
        "Nexus Pharma",
        "City Hospital",
        "Kolkata",
        "Howrah",
        5.5,
        18,
        "High",
        "Picked Up",
        1,
    ),
    (
        "AICMS-1002",
        "TechZone",
        "Retail Point",
        "Delhi",
        "Noida",
        14.0,
        26,
        "Medium",
        "In Transit",
        2,
    ),
    (
        "AICMS-1003",
        "Fresh Farm",
        "Central Market",
        "Mumbai",
        "Navi Mumbai",
        35.0,
        34,
        "Critical",
        "Awaiting Dispatch",
        None,
    ),
]


def get_connection():
    if DATABASE_URL:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def using_postgres():
    return bool(DATABASE_URL)


def adapt_query(query):
    return query.replace("?", "%s") if using_postgres() else query


def execute(cursor, query, params=()):
    return cursor.execute(adapt_query(query), params)


def executemany(cursor, query, params_seq):
    return cursor.executemany(adapt_query(query), params_seq)


def fetch_scalar(cursor, query, params=()):
    execute(cursor, query, params)
    row = cursor.fetchone()
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def initialize_database():
    connection = get_connection()
    cursor = connection.cursor()

    if using_postgres():
        execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS couriers (
                id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                name TEXT NOT NULL,
                hub TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                status TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                current_load INTEGER NOT NULL DEFAULT 0
            )
            """,
        )
        execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                tracking_id TEXT NOT NULL UNIQUE,
                sender_name TEXT NOT NULL,
                receiver_name TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                package_weight DOUBLE PRECISION NOT NULL,
                distance_km DOUBLE PRECISION NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_courier_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (assigned_courier_id) REFERENCES couriers (id)
            )
            """,
        )
    else:
        execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS couriers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hub TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                status TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                current_load INTEGER NOT NULL DEFAULT 0
            )
            """,
        )
        execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_id TEXT NOT NULL UNIQUE,
                sender_name TEXT NOT NULL,
                receiver_name TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                package_weight REAL NOT NULL,
                distance_km REAL NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_courier_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (assigned_courier_id) REFERENCES couriers (id)
            )
            """,
        )

    connection.commit()

    if fetch_scalar(cursor, "SELECT COUNT(*) AS total FROM couriers") == 0:
        executemany(
            cursor,
            """
            INSERT INTO couriers (name, hub, vehicle_type, status, capacity, current_load)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            COURIER_SEED,
        )

    if fetch_scalar(cursor, "SELECT COUNT(*) AS total FROM shipments") == 0:
        executemany(
            cursor,
            """
            INSERT INTO shipments (
                tracking_id, sender_name, receiver_name, origin, destination,
                package_weight, distance_km, priority, status, assigned_courier_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (*shipment, datetime.now().isoformat(timespec="seconds"))
                for shipment in SHIPMENT_SEED
            ],
        )

    connection.commit()
    connection.close()


def fetch_dashboard_data():
    connection = get_connection()
    cursor = connection.cursor()

    summary = {
        "total_shipments": fetch_scalar(cursor, "SELECT COUNT(*) AS total FROM shipments"),
        "active_shipments": fetch_scalar(
            cursor,
            "SELECT COUNT(*) AS total FROM shipments WHERE status IN ('Picked Up', 'In Transit', 'Awaiting Dispatch')",
        ),
        "available_couriers": fetch_scalar(
            cursor,
            "SELECT COUNT(*) AS total FROM couriers WHERE status = 'Available'",
        ),
        "critical_shipments": fetch_scalar(
            cursor,
            "SELECT COUNT(*) AS total FROM shipments WHERE priority = 'Critical'",
        ),
    }

    execute(
        cursor,
        """
        SELECT shipments.*, couriers.name AS courier_name
        FROM shipments
        LEFT JOIN couriers ON shipments.assigned_courier_id = couriers.id
        ORDER BY shipments.id DESC
        """
    )
    shipments = cursor.fetchall()

    execute(cursor, "SELECT * FROM couriers ORDER BY status ASC, current_load ASC, name ASC")
    couriers = cursor.fetchall()

    connection.close()
    return summary, shipments, couriers


def score_courier(courier, shipment):
    if courier["status"] != "Available":
        return -1

    free_capacity = courier["capacity"] - courier["current_load"]
    if free_capacity < shipment["package_weight"]:
        return -1

    vehicle_bonus = {"Bike": 8, "Van": 6, "Truck": 4}.get(courier["vehicle_type"], 2)
    priority_bonus = {"Critical": 20, "High": 14, "Medium": 8, "Low": 4}.get(
        shipment["priority"], 2
    )
    load_bonus = max(0, 25 - courier["current_load"])
    distance_penalty = min(shipment["distance_km"] / 2, 20)
    weight_penalty = min(shipment["package_weight"], 15)

    return round(vehicle_bonus + priority_bonus + load_bonus - distance_penalty - weight_penalty, 2)


def generate_ai_recommendations():
    connection = get_connection()
    cursor = connection.cursor()

    execute(
        cursor,
        "SELECT * FROM shipments WHERE assigned_courier_id IS NULL ORDER BY created_at ASC",
    )
    pending_shipments = cursor.fetchall()
    execute(cursor, "SELECT * FROM couriers")
    couriers = cursor.fetchall()

    recommendations = []
    for shipment in pending_shipments:
        ranked = []
        for courier in couriers:
            score = score_courier(courier, shipment)
            if score >= 0:
                eta_hours = max(1, round((shipment["distance_km"] / 28) + (shipment["package_weight"] / 25), 1))
                ranked.append(
                    {
                        "courier_id": courier["id"],
                        "courier_name": courier["name"],
                        "vehicle_type": courier["vehicle_type"],
                        "hub": courier["hub"],
                        "score": score,
                        "eta_hours": eta_hours,
                    }
                )

        ranked.sort(key=lambda item: (-item["score"], item["eta_hours"], item["courier_name"]))
        recommendations.append(
            {
                "shipment_id": shipment["id"],
                "tracking_id": shipment["tracking_id"],
                "route": f'{shipment["origin"]} -> {shipment["destination"]}',
                "priority": shipment["priority"],
                "weight": shipment["package_weight"],
                "top_matches": ranked[:3],
            }
        )

    connection.close()
    return recommendations


def add_courier(payload):
    connection = get_connection()
    cursor = connection.cursor()
    execute(
        cursor,
        """
        INSERT INTO couriers (name, hub, vehicle_type, status, capacity, current_load)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload["name"],
            payload["hub"],
            payload["vehicle_type"],
            payload["status"],
            int(payload["capacity"]),
            int(payload.get("current_load", 0)),
        ),
    )
    connection.commit()
    connection.close()


def add_shipment(payload):
    connection = get_connection()
    cursor = connection.cursor()
    tracking_id = f"AICMS-{1000 + fetch_scalar(cursor, 'SELECT COUNT(*) AS total FROM shipments') + 1}"
    execute(
        cursor,
        """
        INSERT INTO shipments (
            tracking_id, sender_name, receiver_name, origin, destination,
            package_weight, distance_km, priority, status, assigned_courier_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            tracking_id,
            payload["sender_name"],
            payload["receiver_name"],
            payload["origin"],
            payload["destination"],
            float(payload["package_weight"]),
            float(payload["distance_km"]),
            payload["priority"],
            "Awaiting Dispatch",
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    connection.close()


def assign_shipment(payload):
    connection = get_connection()
    cursor = connection.cursor()
    execute(cursor, "SELECT package_weight FROM shipments WHERE id = ?", (int(payload["shipment_id"]),))
    shipment = cursor.fetchone()

    if not shipment:
        connection.close()
        return

    execute(
        cursor,
        """
        UPDATE shipments
        SET assigned_courier_id = ?, status = 'Picked Up'
        WHERE id = ?
        """,
        (int(payload["courier_id"]), int(payload["shipment_id"])),
    )
    execute(
        cursor,
        """
        UPDATE couriers
        SET current_load = current_load + ?
        WHERE id = ?
        """,
        (float(shipment["package_weight"]), int(payload["courier_id"])),
    )

    connection.commit()
    connection.close()


def update_shipment_status(payload):
    connection = get_connection()
    cursor = connection.cursor()
    execute(
        cursor,
        "UPDATE shipments SET status = ? WHERE id = ?",
        (payload["status"], int(payload["shipment_id"])),
    )
    connection.commit()
    connection.close()


def parse_form_data(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8")
    data = parse_qs(raw)
    return {key: values[0] for key, values in data.items()}


def render_template():
    summary, shipments, couriers = fetch_dashboard_data()
    recommendations = generate_ai_recommendations()

    def shipment_rows():
        rows = []
        for shipment in shipments:
            rows.append(
                f"""
                <tr>
                    <td>{shipment['tracking_id']}</td>
                    <td>{shipment['sender_name']} -> {shipment['receiver_name']}</td>
                    <td>{shipment['origin']} -> {shipment['destination']}</td>
                    <td>{shipment['priority']}</td>
                    <td>{shipment['status']}</td>
                    <td>{shipment['courier_name'] or 'Unassigned'}</td>
                </tr>
                """
            )
        return "".join(rows)

    def courier_rows():
        rows = []
        for courier in couriers:
            utilization = round((courier["current_load"] / courier["capacity"]) * 100, 1)
            rows.append(
                f"""
                <tr>
                    <td>{courier['name']}</td>
                    <td>{courier['hub']}</td>
                    <td>{courier['vehicle_type']}</td>
                    <td>{courier['status']}</td>
                    <td>{courier['current_load']} / {courier['capacity']}</td>
                    <td>{utilization}%</td>
                </tr>
                """
            )
        return "".join(rows)

    def recommendation_cards():
        cards = []
        for item in recommendations:
            if item["top_matches"]:
                matches = "".join(
                    [
                        f"""
                        <li>
                            <strong>{match['courier_name']}</strong> ({match['vehicle_type']}, {match['hub']})
                            <span>AI score: {match['score']} | ETA: {match['eta_hours']} hrs</span>
                        </li>
                        """
                        for match in item["top_matches"]
                    ]
                )
            else:
                matches = "<li>No available courier can safely handle this shipment right now.</li>"

            cards.append(
                f"""
                <article class="card recommendation">
                    <div class="pill">{item['priority']} Priority</div>
                    <h3>{item['tracking_id']}</h3>
                    <p>{item['route']}</p>
                    <p>Weight: {item['weight']} kg</p>
                    <ul>{matches}</ul>
                </article>
                """
            )
        return "".join(cards) or "<p class='empty-state'>All shipments are assigned. The AI queue is clear.</p>"

    status_options = "".join(
        f"<option value='{value}'>{value}</option>"
        for value in ["Awaiting Dispatch", "Picked Up", "In Transit", "Delivered", "Delayed"]
    )

    shipment_options = "".join(
        f"<option value='{shipment['id']}'>{shipment['tracking_id']}</option>"
        for shipment in shipments
    )

    courier_options = "".join(
        f"<option value='{courier['id']}'>{courier['name']}</option>"
        for courier in couriers
    )

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Artificial Intelligence Courier Management System</title>
        <style>
            :root {{
                --bg: #f3efe7;
                --surface: rgba(255, 252, 247, 0.9);
                --ink: #1b1f24;
                --muted: #57606a;
                --brand: #0b6e4f;
                --accent: #f4a259;
                --alert: #b42318;
                --line: rgba(27, 31, 36, 0.1);
                --shadow: 0 20px 45px rgba(27, 31, 36, 0.12);
            }}
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                font-family: Georgia, "Times New Roman", serif;
                background:
                    radial-gradient(circle at top left, rgba(244, 162, 89, 0.35), transparent 28%),
                    linear-gradient(135deg, #efe6d7 0%, #f8f4eb 48%, #e7f1ea 100%);
                color: var(--ink);
            }}
            .shell {{
                max-width: 1320px;
                margin: 0 auto;
                padding: 28px 18px 48px;
            }}
            .hero {{
                background: linear-gradient(135deg, rgba(11, 110, 79, 0.96), rgba(16, 62, 83, 0.92));
                color: #f7f3eb;
                border-radius: 28px;
                padding: 32px;
                box-shadow: var(--shadow);
                overflow: hidden;
                position: relative;
            }}
            .hero::after {{
                content: "";
                position: absolute;
                inset: auto -80px -80px auto;
                width: 280px;
                height: 280px;
                border-radius: 50%;
                background: rgba(244, 162, 89, 0.14);
            }}
            h1, h2, h3 {{
                margin: 0 0 12px;
                font-weight: 700;
                letter-spacing: 0.02em;
            }}
            .hero p {{
                max-width: 720px;
                margin: 0;
                color: rgba(247, 243, 235, 0.84);
                line-height: 1.6;
            }}
            .grid {{
                display: grid;
                gap: 18px;
                margin-top: 22px;
            }}
            .metrics {{
                grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            }}
            .card {{
                background: var(--surface);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.45);
                border-radius: 22px;
                padding: 20px;
                box-shadow: var(--shadow);
            }}
            .metric-value {{
                font-size: 2.2rem;
                color: var(--brand);
            }}
            .section-layout {{
                display: grid;
                grid-template-columns: 1.1fr 0.9fr;
                gap: 18px;
                margin-top: 22px;
            }}
            .section-stack {{
                display: grid;
                gap: 18px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.96rem;
            }}
            th, td {{
                padding: 12px 10px;
                text-align: left;
                border-bottom: 1px solid var(--line);
                vertical-align: top;
            }}
            th {{
                color: var(--muted);
                font-size: 0.82rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }}
            form {{
                display: grid;
                gap: 10px;
            }}
            input, select, button {{
                width: 100%;
                border-radius: 14px;
                border: 1px solid var(--line);
                padding: 12px 14px;
                font: inherit;
                background: rgba(255,255,255,0.85);
            }}
            button {{
                background: linear-gradient(135deg, var(--brand), #155e75);
                color: white;
                border: none;
                cursor: pointer;
                font-weight: 700;
            }}
            button:hover {{
                filter: brightness(1.06);
            }}
            .pill {{
                display: inline-flex;
                padding: 7px 12px;
                border-radius: 999px;
                background: rgba(244, 162, 89, 0.18);
                color: #8f4b08;
                font-size: 0.82rem;
                margin-bottom: 12px;
            }}
            .recommendation ul {{
                padding-left: 18px;
                margin: 10px 0 0;
            }}
            .recommendation li {{
                margin-bottom: 10px;
                line-height: 1.5;
            }}
            .recommendation span {{
                display: block;
                color: var(--muted);
                font-size: 0.92rem;
            }}
            .forms {{
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            }}
            .empty-state {{
                color: var(--muted);
            }}
            .footer-note {{
                margin-top: 18px;
                color: var(--muted);
                font-size: 0.92rem;
            }}
            @media (max-width: 960px) {{
                .section-layout {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="shell">
            <section class="hero">
                <div class="pill">AI Operations Dashboard</div>
                <h1>Artificial Intelligence Courier Management System</h1>
                <p>
                    Monitor couriers, track shipments, and use a lightweight AI scoring engine to match urgent
                    deliveries with the best available fleet capacity in real time.
                </p>
            </section>

            <section class="grid metrics">
                <article class="card">
                    <p>Total Shipments</p>
                    <div class="metric-value">{summary['total_shipments']}</div>
                </article>
                <article class="card">
                    <p>Active Shipments</p>
                    <div class="metric-value">{summary['active_shipments']}</div>
                </article>
                <article class="card">
                    <p>Available Couriers</p>
                    <div class="metric-value">{summary['available_couriers']}</div>
                </article>
                <article class="card">
                    <p>Critical Requests</p>
                    <div class="metric-value" style="color: var(--alert);">{summary['critical_shipments']}</div>
                </article>
            </section>

            <section class="section-layout">
                <article class="card">
                    <h2>Shipment Monitoring</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Tracking</th>
                                <th>Parties</th>
                                <th>Route</th>
                                <th>Priority</th>
                                <th>Status</th>
                                <th>Courier</th>
                            </tr>
                        </thead>
                        <tbody>{shipment_rows()}</tbody>
                    </table>
                </article>

                <div class="section-stack">
                    <article class="card">
                        <h2>AI Dispatch Suggestions</h2>
                        <div class="grid">{recommendation_cards()}</div>
                    </article>
                    <article class="card">
                        <h2>Fleet Utilization</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>Courier</th>
                                    <th>Hub</th>
                                    <th>Vehicle</th>
                                    <th>Status</th>
                                    <th>Load</th>
                                    <th>Used</th>
                                </tr>
                            </thead>
                            <tbody>{courier_rows()}</tbody>
                        </table>
                    </article>
                </div>
            </section>

            <section class="grid forms">
                <article class="card">
                    <h2>Add Courier</h2>
                    <form method="POST" action="/couriers">
                        <input name="name" placeholder="Courier name" required>
                        <input name="hub" placeholder="Hub location" required>
                        <select name="vehicle_type">
                            <option>Bike</option>
                            <option>Van</option>
                            <option>Truck</option>
                        </select>
                        <select name="status">
                            <option>Available</option>
                            <option>On Route</option>
                            <option>Off Duty</option>
                        </select>
                        <input name="capacity" type="number" min="1" placeholder="Capacity (kg)" required>
                        <input name="current_load" type="number" min="0" placeholder="Current load (kg)" value="0">
                        <button type="submit">Save Courier</button>
                    </form>
                </article>

                <article class="card">
                    <h2>Create Shipment</h2>
                    <form method="POST" action="/shipments">
                        <input name="sender_name" placeholder="Sender name" required>
                        <input name="receiver_name" placeholder="Receiver name" required>
                        <input name="origin" placeholder="Origin city" required>
                        <input name="destination" placeholder="Destination city" required>
                        <input name="package_weight" type="number" min="1" step="0.1" placeholder="Package weight (kg)" required>
                        <input name="distance_km" type="number" min="1" step="0.1" placeholder="Distance (km)" required>
                        <select name="priority">
                            <option>Low</option>
                            <option>Medium</option>
                            <option>High</option>
                            <option>Critical</option>
                        </select>
                        <button type="submit">Create Shipment</button>
                    </form>
                </article>

                <article class="card">
                    <h2>Assign Shipment</h2>
                    <form method="POST" action="/assign">
                        <select name="shipment_id">{shipment_options}</select>
                        <select name="courier_id">{courier_options}</select>
                        <button type="submit">Assign with AI Queue</button>
                    </form>
                </article>

                <article class="card">
                    <h2>Update Status</h2>
                    <form method="POST" action="/status">
                        <select name="shipment_id">{shipment_options}</select>
                        <select name="status">{status_options}</select>
                        <button type="submit">Update Shipment Status</button>
                    </form>
                    <p class="footer-note">
                        Tip: create a shipment, then use the AI suggestions panel to decide the most suitable courier.
                    </p>
                </article>
            </section>
        </div>
    </body>
    </html>
    """


class CourierManagementHandler(BaseHTTPRequestHandler):
    def _redirect_home(self):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/recommendations":
            payload = json.dumps(generate_ai_recommendations()).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")
            return

        html = render_template().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = parse_form_data(self)

        if parsed.path == "/couriers":
            add_courier(payload)
            self._redirect_home()
            return

        if parsed.path == "/shipments":
            add_shipment(payload)
            self._redirect_home()
            return

        if parsed.path == "/assign":
            assign_shipment(payload)
            self._redirect_home()
            return

        if parsed.path == "/status":
            update_shipment_status(payload)
            self._redirect_home()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Action not found")


def run():
    initialize_database()
    server = HTTPServer((HOST, PORT), CourierManagementHandler)
    print(f"AI Courier Management System running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
