# Backend Improvement Specification & Implementation Plan

## Overview
The SCADA Reporter backend is currently handling a massive 8GB SQLite database and serving both API requests and data polling within the same process. To improve scalability, real-time performance, and reliability, we will implement two key architectural improvements.

## 1. WebSocket Integration for Live Data
**Problem**: The frontend currently polls the `/dashboard/*` endpoints every 5 seconds to get live tag readings. This creates unnecessary HTTP overhead and a minimum 5-second latency.
**Solution**: Implement a FastAPI WebSocket endpoint to stream live tag data to connected clients as it arrives.
- **Location**: `backend/app/api/dashboard.py`
- **Endpoint**: `GET /dashboard/stream` (WebSocket)
- **Mechanism**:
  - Accept WebSocket connections authenticated via query parameters or initial auth message.
  - Listen to a Redis Pub/Sub channel (or internal async queue/broadcast if single-node) for tag updates.
  - The Poller (Collector) will push new readings into this broadcast channel.
  - The WebSocket endpoint will push the updated JSON to the frontend immediately.

## 2. Process Decoupling (API vs Collector)
**Problem**: The API, Scheduler, and Collector (OPC UA / S7 Poller) run in the same process by default (`RUN_COLLECTOR=True`). Heavy API loads can block the polling loop, and vice-versa.
**Solution**: Provide a clean way to separate the API workers from the background polling workers using the existing `config.py` flags.
- **Location**: `backend/run_worker.py` / `backend/docker-compose.yml` (if applicable)
- **Mechanism**:
  - Create a dedicated worker script (e.g., `backend/run_worker.py`) that strictly runs the collector and scheduler (`RUN_COLLECTOR=True`, API server off).
  - Modify the main API entrypoint to default to `RUN_COLLECTOR=False` in production.

## Implementation Steps for Subagent
1. **WebSocket Endpoint**:
   - In `app/api/dashboard.py`, add an `@router.websocket("/stream")` endpoint.
   - For now, since Redis might not be strictly required for a single-node setup, implement an in-memory async broadcast system (e.g., a simple pub/sub using `asyncio.Queue` or a global list of connected clients).
   - *Alternative*: If `app/core/log_buffer.py` or similar already has a broadcast mechanism, reuse it.
2. **Collector Push**:
   - In the collector logic (where `TagReading` is inserted), push the new values to the broadcast system so the WebSocket can emit them.
3. **Decoupling Script**:
   - Create `backend/run_worker.py` that initializes the database and starts the collector loop without booting uvicorn/FastAPI.

*Note: Please implement step 1 (WebSockets) in `dashboard.py` as the primary objective.*
