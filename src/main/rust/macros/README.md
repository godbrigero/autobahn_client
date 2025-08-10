## DO NOT USE THIS UNLESS YOU ARE USING AUTOBAHN_CLIENT LIBRARY! This WILL NOT WORK.

autobahn-client-macros

Procedural macros for `autobahn-client` that generate RPC client and server glue code.

Highlights:

- `#[client_function]` to generate typed RPC client calls
- `#[server_function]` to register server-side RPC handlers

Add to your Cargo.toml:

```
[dependencies]
autobahn-client-macros = "0.1"
```

License: MIT
