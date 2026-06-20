# Tüm REST yolları — tek kaynak. Hiçbir başka modül URL stringi yazmaz.

AUTH_TOKEN = "api/auth/token"
AUTH_REGISTER = "api/auth/register"
AUTH_ME = "api/auth/me"

TAGS = "api/tags/"
TAG_ITEM = "api/tags/{tag_id}"
TAG_READINGS = "api/tags/{tag_id}/readings"

DASHBOARD_TAGS = "api/dashboard/tags"  # latest reading + quality (current values)
DASHBOARD_OVERVIEW = "api/dashboard/overview"
TREND = "api/dashboard/trend"  # tag_ids + hours
TREND_RANGE = "api/dashboard/trend_range"  # tag_ids + start + end

PLC = "api/plc/"

QUERY_RUN = "api/query/run"  # body {sql, params, limit}

EXPLORE_SCHEMA = "api/explore/schema"
EXPLORE_SUMMARY = "api/explore/summary"

REPORTS_GENERATE = "api/reports/generate"
REPORTS_HISTORY = "api/reports/history"

AI_ANOMALIES = "api/ai/anomalies"
AI_PREDICT = "api/ai/predict"
AI_RESOLVE = "api/ai/resolve"
AI_REPORTS_GENERATE = "api/ai/reports/generate"
AI_HEALTH = "api/ai/health"
AI_QUERY = "api/ai/query"

HEALTH = "health"
