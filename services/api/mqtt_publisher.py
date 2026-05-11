# Stage 6 compatibility shim — real implementation moved to adapters/mqtt/publisher.py
# This file exists so any tooling or documentation referencing the old path still works.
# It will be removed in Stage 7 once all references are confirmed updated.
from adapters.mqtt.publisher import publish_command  # noqa: F401
