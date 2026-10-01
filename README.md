# Railway Safety — Kafka + Grafana

A college project that simulates a railway safety monitoring system using Kafka, MySQL and Grafana.

## What the project does

Simulated railway sensors continuously publish:

- Rail temperature
- Weather conditions
- Train movement and speed

Kafka carries these live streams to the **buckling engine**. The engine combines the latest rail temperature, RNT, track condition, track curvature and train speed to calculate a simplified operational buckling-risk score.

The result is:

```text
Sensors / Train Data
        ↓
      Kafka
        ↓
  Buckling Engine
        ↓
      MySQL
        ↓
     Grafana
```

The train simulation also consumes the risk topic so an elevated-risk event can reduce the simulated train speed. This demonstrates the Kafka feedback loop.

> **Important:** The buckling model is an academic simulation, not a railway engineering or safety-certified model. The recommended speeds are simulated project outputs, not real operating limits.

## Existing local services

This project uses the containers already provided by the course setup:

```text
Kafka    → localhost:9092
MySQL    → localhost:3306
Grafana  → http://localhost:3000
```

Make sure those Docker containers are running before starting the Python programs.

## One-time setup

### 1. Install Python dependencies

Activate your existing virtual environment, then run:

```powershell
pip install -r requirements.txt
```

### 2. Add the MySQL password

Open `config.py` and set:

```python
MYSQL_PASSWORD = "YOUR_MYSQL_PASSWORD"
```

Do not commit a real password to a public GitHub repository.

### 3. Create the database and track data

Run:

```powershell
python setup_project.py
```

This creates the `railway_safety` database/tables, resets the dynamic event tables, generates the simulated track geometry CSV, and loads the track data into MySQL.

### 4. Publish static track geometry to Kafka

Run once after setup:

```powershell
python track_producer.py
```

You should see:

```text
Published ... track geometry points to 'track-geometry'.
```

## Run the live project

Start the four live Python processes with:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_live.ps1
```

This starts:

```text
weather_producer.py
rail_temperature_producer.py
train_movement_producer.py
buckling_engine.py
```

Leave these windows running while using Grafana.

Open:

```text
http://localhost:3000
```

Set the Grafana MySQL data source to the `railway_safety` database if it is not already configured.

## Stop the project

Press:

```text
Ctrl + C
```

in the live Python windows.

You normally do **not** need to rerun `setup_project.py` every time. Run it again only when you intentionally want to reset the dynamic event data for a fresh demo.

## Kafka topics

```text
track-geometry
weather-events
rail-temperature-events
train-movement-events
buckling-risk-events
```

## Main files

| File | Purpose |
|---|---|
| `config.py` | Kafka, MySQL, train and simulation settings |
| `setup_project.py` | Creates/reset database and track data |
| `track_geometry.py` | Simulated railway geometry and track properties |
| `track_producer.py` | Publishes static track geometry to Kafka |
| `weather_producer.py` | Publishes simulated weather data |
| `rail_temperature_producer.py` | Publishes simulated rail-temperature sensor data |
| `train_movement_producer.py` | Publishes train movement and consumes risk responses |
| `buckling_model.py` | Calculates the simplified buckling/operational risk |
| `buckling_engine.py` | Kafka consumer that combines streams, calculates risk and writes MySQL |
| `mysql_db.py` | MySQL connection and insert helpers |
| `simulation.py` | Shared simulation time/environment logic |
| `start_live.ps1` | Starts the live Python processes |
| `grafana_dashboard.json` | Optional dashboard export/backup |

## Grafana dashboard

The dashboard can use a `Train_ID` variable to follow one train at a time.

Useful panels include:

- Rail Temperature vs Stress-Free Temperature (RNT)
- Current Train Number
- Current Track
- Current Speed
- Recommended Speed
- Current Buckling Risk
- Buckling Risk Score Over Time
- Temperature Above RNT
- Current Risk by Track Segment

Refresh the dashboard every few seconds for the live demonstration.


