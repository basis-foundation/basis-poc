# Stage 6 compatibility shim — real implementation moved to adapters/mqtt/subscriber.py
# This file exists so any tooling or documentation referencing the old path still works.
# It will be removed in Stage 7 once all references are confirmed updated.
from adapters.mqtt.subscriber import mqtt_listener  # noqa: F401
