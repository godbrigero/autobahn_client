Autobahn Client (Rust)

This crate provides a client implementation and RPC helpers for the Autobahn hub, powered by Prost-based protobuf messages and `tokio` websockets.

Highlights:

- WebSocket client with RPC request/response helpers
- Procedural macros via `autobahn-client-macros` for declaring RPC client/server functions
- Builds protobufs from the bundled `proto/` directory at compile time

Usage

Add to your Cargo.toml:

```
[dependencies]
autobahn-client = "0.1"
```

See examples in the repository for end-to-end usage.

License: MIT
