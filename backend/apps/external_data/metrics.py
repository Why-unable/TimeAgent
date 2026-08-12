from prometheus_client import Counter, Histogram

REVERSE_GEOCODING_REQUESTS = Counter(
    "time_agent_reverse_geocoding_requests_total",
    "Reverse geocoding attempts grouped by provider and result.",
    ("provider", "result"),
)
REVERSE_GEOCODING_DURATION = Histogram(
    "time_agent_reverse_geocoding_duration_seconds",
    "Reverse geocoding provider latency in seconds.",
    ("provider",),
)
