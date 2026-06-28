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
READY = "ready"

# --- Spec 2: write endpoints ---
WATCHLIST_ITEM = "api/dashboard/watchlist/{tag_id}"

ANNOTATIONS = "api/annotations/"
ANNOTATION_ITEM = "api/annotations/{annotation_id}"

ADV_TEMPLATES = "api/advanced-reports/templates"
ADV_TEMPLATE_ITEM = "api/advanced-reports/templates/{template_id}"
ADV_TEMPLATE_RUN = "api/advanced-reports/templates/{template_id}/run"
ADV_SCHEDULED = "api/advanced-reports/scheduled"
ADV_SCHEDULED_ITEM = "api/advanced-reports/scheduled/{scheduled_id}"
ADV_SCHEDULED_TOGGLE = "api/advanced-reports/scheduled/{scheduled_id}/toggle"
ADV_ARCHIVE_ITEM = "api/advanced-reports/archive/{archive_id}"

GROUPS = "api/groups/"
GROUP_ITEM = "api/groups/{group_id}"
GROUP_ASSIGN = "api/groups/{group_id}/assign"
GROUP_UNASSIGN = "api/groups/unassign"

PLC_ITEM = "api/plc/{name}"

USERS = "api/users/"
USER_ITEM = "api/users/{user_id}"
USER_PASSWORD = "api/users/{user_id}/password"

# --- Compliance read surface ---
COMPLIANCE_OVERVIEW = "/api/compliance/overview"
COMPLIANCE_EVENTS = "/api/compliance/events"
COMPLIANCE_EVALUATE = "/api/compliance/evaluate"
