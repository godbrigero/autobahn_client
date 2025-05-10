# Autobahn Client

A Python client for Autobahn.

## Installation

```bash
pip install autobahn_client
```

## Usage

```python
from autobahn_client import AutobahnClient
from autobahn_client.proto.message_pb2 import MessageType

# Create a client
client = AutobahnClient()

# Connect to the service
client.connect()

# Publish a message to a topic
message = client.publish("my-topic", "Hello, world!")
print(f"Published message to {message.topic}")

# Subscribe to a topic
subscription = client.subscribe("another-topic")
print(f"Subscribed to {subscription.topic}")
```

## Working with Protocol Buffers

This package uses Protocol Buffers for message serialization. The protobuf definitions are located in the `src/proto/` directory.

### Compiling Proto Files

If you make changes to the `.proto` files, you need to recompile them:

```bash
# Install the protobuf compiler if you haven't already
# macOS: brew install protobuf
# Ubuntu/Debian: apt-get install protobuf-compiler

# Compile the proto files
python scripts/compile_protos.py
```

## License

MIT
