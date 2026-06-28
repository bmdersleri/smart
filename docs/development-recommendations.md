# EKONT SMART REPORT - Development Recommendations

This document outlines detailed architectural and developmental recommendations for the EKONT SMART REPORT project, focusing on optimizing both the Python backend and the React frontend. These suggestions aim to enhance scalability, performance, and user experience, especially given the high-throughput nature of SCADA systems.

---

## Backend Recommendations (FastAPI, SQLAlchemy, PostgreSQL)

### 1. Data Collection & Poller Optimization (`app/collector`)

*   **Parallel PLC Communication:** Currently, data collection runs periodically (default 5s) via `s7_collector.py` and `poller.py`. As the number of tags grows (currently 3000+) or multiple PLCs are added, sequential reading may exceed the polling interval.
    *   *Implementation:* Use `asyncio.gather` to concurrently read from multiple PLCs or multiple independent data blocks within the same PLC.
*   **Aggressive Deadband Filtering:** To prevent database bloat, refine the deadband logic. Only persist values to the database if they exceed a specific percentage or absolute threshold of change compared to the last recorded value. For critical boolean states (alarms/motors), ensure state transitions are always recorded immediately.
*   **Circuit Breaker Pattern:** Implement a circuit breaker in the PLC connection logic. If a PLC becomes unreachable, the poller should gracefully back off rather than hanging or continuously timing out, which can starve the event loop.

### 2. Time-Series Database Optimization (TimescaleDB)

*   **Hypertable Tuning:** Ensure that the `TagReading` table is correctly converted into a TimescaleDB hypertable partitioned by the `timestamp` column. Adjust the chunk time interval based on your data volume (e.g., 1 day or 7 days) to ensure chunks fit into RAM.
*   **Continuous Aggregates:** The reporting system frequently queries hourly or daily summaries. Instead of aggregating raw data on the fly via SQLAlchemy, leverage TimescaleDB's Continuous Aggregates. This creates background materialized views that pre-calculate averages, maximums, and minimums, reducing complex report generation times from seconds to milliseconds.
*   **Data Retention Policies:** Implement TimescaleDB's native data retention policies (`add_retention_policy`) to automatically drop raw data older than a certain threshold (e.g., 3 months) while keeping the downsampled Continuous Aggregates indefinitely.

### 3. Architecture & Code Quality

*   **Repository Pattern (DAO):** Introduce a Repository layer between `app/services` and `app/models`. Currently, services likely interact with SQLAlchemy sessions directly. Decoupling this logic makes the services easier to unit test (by mocking the repository) and centralizes complex SQL queries.
*   **Test Coverage Goal:** The `pyproject.toml` sets the test coverage baseline to `fail_under = 69`. Gradually increase this target to 80%+. Prioritize writing robust integration tests for the report generation engine and the PLC poller's error-handling paths.

---

## Frontend Recommendations (React 19, Vite, Tailwind CSS v4)

### 1. Real-Time State Management (TanStack Query + SSE)

*   **Optimistic Cache Updates via SSE:** The application utilizes Server-Sent Events (SSE) at `/api/dashboard/stream`. Instead of treating SSE as a separate data stream, pipe the incoming SSE messages directly into TanStack Query's cache using `queryClient.setQueryData`. This immediately updates the UI without requiring TanStack Query to perform HTTP refetches, saving bandwidth and eliminating UI latency.
*   **Stale-Time Tuning:** For data that updates strictly via SSE, set the TanStack Query `staleTime` to `Infinity` to prevent background refetching entirely.

### 2. High-Performance Charting (`recharts`)

*   **Data Downsampling (Decimation):** SCADA trend charts can easily attempt to render tens of thousands of data points (e.g., 24 hours of data logged every 5 seconds). `recharts` (SVG-based) will struggle with DOM bloat under these conditions.
    *   *Implementation:* Implement a downsampling algorithm like LTTB (Largest Triangle Three Buckets) either on the backend or inside a Web Worker on the frontend. LTTB reduces the dataset size while preserving the visual shape and peaks/valleys of the trend.
*   **Canvas Fallback:** If trend charts become too complex (multi-axis, high density), consider evaluating a Canvas/WebGL-based charting library like Apache ECharts or uPlot for the specific "Trend Chart" page, as they handle massive datasets significantly better than SVG-based libraries.

### 3. Industrial UI / UX Aesthetics

*   **Move Beyond "Boring SCADA":** Leverage Tailwind CSS v4 to introduce modern UI paradigms. Use subtle *Glassmorphism* (backdrop-blur) for floating panels or tooltips, and ensure a highly polished Dark Mode since SCADA operators often work in dimly lit control rooms.
*   **Micro-animations for Status:** Instead of relying solely on static colors (Red = Alarm, Green = Running), use Tailwind's animation utilities. A softly pulsing indicator (`animate-pulse`) for active alarms draws the operator's eye much faster. Use smooth transitions (`transition-all duration-300`) for numeric values that change rapidly to reduce visual harshness.
*   **Iconography:** Ensure consistent use of `lucide-react` icons across all navigation, buttons, and status indicators.

### 4. Internationalization (i18n) & RTL Layouts

*   **Logical CSS Properties:** The application supports Arabic, requiring a Right-to-Left (RTL) layout. When styling with Tailwind CSS, strictly use logical properties. Replace physical margins/paddings like `ml-` (margin-left) or `pr-` (padding-right) with `ms-` (margin-start) and `pe-` (padding-end). This ensures the layout automatically mirrors itself flawlessly when the user switches to an RTL language without needing manual direction checks.
