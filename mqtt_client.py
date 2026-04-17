import paho.mqtt.client as mqtt
import json

class MQTTClient:
    def __init__(self, token, host="mqtt.thingsboard.cloud", port=1883, topic="v1/devices/me/telemetry"):
        if not token:
            raise ValueError("ThingsBoard token is required")

        self.host = host
        self.port = port
        self.topic = topic
        self.connected = False

        self.client = mqtt.Client(protocol=mqtt.MQTTv311)
        self.client.username_pw_set(token)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False

    def _ensure_connected(self):
        if self.connected:
            return True
        try:
            self.client.reconnect()
            return True
        except Exception:
            return False

    def send(self, data):
        if not self._ensure_connected():
            return False
        message = self.client.publish(self.topic, json.dumps(data), qos=1)
        message.wait_for_publish(timeout=2)
        return message.rc == mqtt.MQTT_ERR_SUCCESS

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()