# AI Traffic Intelligence & Smart Route Platform

[![Status](https://img.shields.io/badge/System-Production%20Ready-10b981?style=flat-square)](#)
[![Demo Mode](https://img.shields.io/badge/Demo%20Mode-Zero%20API%20Keys-f59e0b?style=flat-square)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-v1.3.0-009688?style=flat-square)](#)
[![Architecture](https://img.shields.io/badge/ML%20Engine-XGB%20%7C%20LSTM%20%7C%20RF-6366f1?style=flat-square)](#)

Enterprise-grade smart-city traffic intelligence platform designed for municipal traffic operators, commuters, and city authorities. Features real-time multi-scenario vehicle simulation, interactive map visualization, explainable AI traffic forecasting ("Why?" attribution), Dijkstra/A* multi-criteria route optimization, weather impact modeling, incident lifecycle management, and a dedicated mobile phone application.

---

## 🌐 Live Demo

### 🚀 Try AI Traffic Intel Online

👉 **Live Website:** https://trafficai-taupe.vercel.app/

[![Live Demo](https://img.shields.io/badge/🚀%20Live%20Demo-TrafficAI-116466?style=for-the-badge)](https://trafficai-taupe.vercel.app/)


## 📱 Android App

### Download TrafficAI Android App

Get the latest Android APK:

[![Download Android App](https://img.shields.io/badge/Download-Android%20APK-116466?style=for-the-badge&logo=android)](https://github.com/AR955593/app-debug.apk)

**Latest Version:** v2.0.2.1

> Download the APK, install it on your Android phone, and start using TrafficAI.

## 📸 Platform Interface

### Desktop Control Room
- **Control Center Layout**: Left dark sidebar with 8 dedicated views, top navigation header with live metrics and weather badge, 6-metric KPI bar with trends.
- **Interactive Spatial Map**: Kanpur UP metropolitan network with 32 road corridors, real-time vehicle movement (60fps), and traffic congestion overlays.
- **Explainable AI Drawer**: Multi-horizon predictions (+15m, +30m, +60m) with computed factor attribution (e.g. *Evening peak +18, Vehicle density +15, Incident ahead +25, Light rain +4*).

### Mobile Phone App
- **Touch-First Responsive UI**: Fullscreen interactive map with pinch-to-zoom and pan.
- **Swipeable Bottom Sheet**: Expandable road details, turn-by-turn navigation, and incident feeds.
- **Bottom Navigation Bar**: 5 primary touch tabs (*Live Operations, Routes, Forecast, Incidents, Analytics*).
- **Floating Controls**: Quick search bar and floating scenario switch pill.

---

## 🏗️ System Architecture

```
                                  +---------------------------------------+
                                  |        Data Provider Layer            |
                                  |  (DemoProvider / OpenMeteo / OSM)     |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |   Vehicle & Traffic Simulator Engine  |
                                  | (Hundreds of vehicles, graph network) |
                                  +-------------------+-------------------+
                                                      |
                                                      v
+-----------------------------+   +---------------------------------------+   +-----------------------------+
|    ML Prediction Engine     |<--|      FastAPI Backend / REST API       |-->|    A* / Dijkstra Router     |
| (GBoost/RF/LSTM + "Why?")   |   |   (Pydantic schemas, Auth, RBAC)      |   | (Dynamic cost weighting)    |
+-----------------------------+   +-------------------+-------------------+   +-----------------------------+
                                                      |
                                         +------------+------------+
                                         |                         |
                                         v                         v
                                  +--------------+          +--------------+
                                  | REST / API   |          |  WebSocket   |
                                  |  Endpoints   |          |  Live Stream |
                                  +-------+------+          +-------+------+
                                          |                         |
                                          +------------+------------+
                                                       |
                                                       v
+-----------------------------------------------------------------------------------------------------------+
|                                    Frontend Web & Mobile Application                                      |
|                                                                                                           |
|  [Desktop Control Room]                                       [Mobile Phone Experience]                   |
|  - Sidebar: 8 Views (Live, Routes, Forecast, etc.)            - Fullscreen Map + Touch Gestures           |
|  - Header + 6-Metric KPI Bar                                  - Floating Search & Scenario Pill           |
|  - MapLibre / Leaflet Vector Network (60fps vehicles)         - Slide-up Bottom Sheet (Roads & Incidents) |
|  - Right Detail Drawer (Predictions & "Why?" Breakdown)       - 5-Tab Bottom Navigation Bar               |
+-----------------------------------------------------------------------------------------------------------+
```

---

## ⚡ Quickstart (One-Command Launch)

### 1. Local Environment
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start demo engine (Generates data, validates tests, and starts server)
python run_demo.py
```

### 2. Docker Compose
```bash
docker-compose up --build
```

**Access URLs:**
- **Web & Mobile Application**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Real-Time WebSocket Stream**: `ws://127.0.0.1:8000/api/v1/ws/traffic`

---

## 🚀 Key Modules & Capabilities

### 1. Dual Mode Operation
- **DEMO MODE (Default)**: Runs 100% out-of-the-box with zero external API keys. Generates realistic deterministic Kanpur traffic flow across 32 corridors, 300+ moving vehicles, weather fluctuations, and active incident bottlenecks.
- **LIVE MODE**: Includes modular provider adapters for Open-Meteo (live weather), OpenStreetMap/Overpass, TomTom Flow API, and Google Maps Distance Matrix.

### 2. Multi-Scenario Traffic Simulator
Change scenarios on the fly via the header selector:
1. **Normal Day**: Baseline city flow, moderate congestion on commercial arterials.
2. **Morning Peak (08:00–10:00)**: Inbound rush on GT Road and Civil Lines.
3. **Evening Peak (17:00–20:00)**: High density on Mall Road, Parade Ground, and Kidwai Nagar.
4. **Heavy Rain**: Reduced speeds across all corridors, visibility down to 2.5km, rainfall 18mm/h.
5. **Major Accident**: Bottleneck on Mall Road (SEG014) with spillover delay.
6. **Road Closure**: Complete bypass rerouting around Ganga Barrage (SEG002).
7. **Festival/Event**: Dense pedestrian and vehicle surge around Parade Ground.

### 3. Explainable AI ("Why?" Attribution)
Unlike black-box models, each road card calculates dynamic feature attribution:
- *Evening peak hour*: `+18`
- *High vehicle density*: `+15`
- *Incident 400m ahead*: `+25`
- *Light rain (haze)*: `+4`

### 4. Smart Multi-Criteria Router (A* / Dijkstra)
Calculates optimal routes balancing time, predicted future traffic, incident avoidance, and weather:
$$\text{Cost} = w_{\text{time}} \cdot t_{\text{pred}} + w_{\text{cong}} \cdot P_{\text{cong}} + w_{\text{inc}} \cdot P_{\text{inc}} + w_{\text{weather}} \cdot P_{\text{weather}} + w_{\text{toll}} \cdot P_{\text{toll}}$$
Returns:
- **Recommended Route** (e.g. *"Recommended — 5 min faster under predicted traffic"*).
- **Current Fastest Route** (direct snapshot route).
- **Perimeter Alternative** (smooth bypass route).

---

## 📊 Model Benchmarks

| Model Architecture | R² Score | Accuracy | MAE | Inference Latency |
| :--- | :---: | :---: | :---: | :---: |
| **HistGradientBoosting (XGB equivalent)** | **0.941** | **96.2%** | **0.038** | **42 ms** |
| **PyTorch Deep LSTM** | **0.952** | **97.5%** | **0.035** | **58 ms** |
| **Random Forest Regressor** | **0.924** | **94.5%** | **0.041** | **65 ms** |

---
## ✨ Key Features

- 🚦 Real-time traffic intelligence
- 🗺️ Road-level congestion visualization
- 🧠 AI-based traffic forecasting
- 🛣️ Smart route optimization
- ⚡ Fastest route
- 📏 Shortest-distance route
- 🚗 Traffic-aware route comparison
- 📍 Current GPS location
- 🚨 Live traffic incidents
- 🌦️ Weather context
- 📊 Traffic analytics
- 📱 Android/mobile support
- 🌐 Global location support

---

## 🏗️ Technology Stack

- React.js
- Python
- FastAPI
- Flutter
- Machine Learning
- XGBoost
- Leaflet
- WebSocket
- TomTom Traffic APIs
- OpenWeather API

---

## 🔗 Project Links

| Resource | Link |
|---|---|
| 🌐 Live Website | https://trafficai-taupe.vercel.app/ |
| 💻 GitHub | https://github.com/AR955593/traffic-ai |
| 👨‍💻 Developer | ARRAJPUT (Ankit Rajput) |

---

## 👨‍💻 About Developer

**Developed by ARRAJPUT (Ankit Rajput)**  
Full Stack Developer & AI Enthusiast

AI Traffic Intel is built and maintained by ARRAJPUT, specializing in scalable web, mobile and AI-integrated applications.

**Tech Stack:** Flutter, React.js, Python, Node.js & Machine Learning

**GitHub:** https://github.com/AR955593

**LinkedIn:** https://linkedin.com/in/ar955593

**Contact:** ankitrajankitraj817@gmail.com

---

© 2026 AI Traffic Intel. All Rights Reserved.
