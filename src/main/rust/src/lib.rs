#![allow(unused_imports)]
pub mod autobahn;
pub use autobahn_client_macros::{client_function, server_function};
pub mod rpc;
pub mod util;

static AUTOBAHN_RPC_PREFIX: &str = "RPC/FUNCTIONAL_SERVICE/";
static AUTOBAHN_RPC_OUTPUT_PREFIX: &str = "RPC/FUNCTIONAL_SERVICE/OUTPUT/";

#[derive(Clone, prost::Message)]
struct MathRequest {
    #[prost(int32, tag = "1")]
    a: i32,
    #[prost(int32, tag = "2")]
    b: i32,
}

#[derive(Clone, prost::Message)]
struct MathResponse {
    #[prost(int32, tag = "1")]
    result: i32,
}

pub mod proto {
    pub mod autobahn {
        include!(concat!(env!("OUT_DIR"), "/proto.autobahn.rs"));
    }
}

#[cfg(test)]
mod tests {
    use std::{thread::sleep, time::Duration};

    use super::*;

    mod server {
        use super::*;
        use autobahn_client_macros::server_function;

        #[server_function]
        pub async fn add_numbers(request: MathRequest) -> MathResponse {
            println!("Processing add request: {} + {}", request.a, request.b);
            MathResponse {
                result: request.a + request.b,
            }
        }

        #[server_function]
        pub async fn get_status() {
            println!("get_status");
        }

        #[server_function]
        pub async fn error_out() {
            panic!("error_out");
        }
    }

    mod client {
        use super::*;
        use autobahn_client_macros::client_function;

        #[client_function]
        pub async fn add_numbers(request: MathRequest) -> MathResponse {
            MathResponse { result: 0 }
        }

        #[client_function]
        pub async fn get_status() {
            println!("get_status");
        }

        #[client_function]
        pub async fn error_out() {
            panic!("error_out");
        }
    }

    // Example 2: Function with no parameters
    #[client_function]
    async fn get_status() {
        println!("get_status");
    }

    #[server_function]
    async fn get_status_server() {
        println!("get_status_server");
    }

    #[tokio::test]
    async fn test_rpc_usage() {
        // This shows how the client and server functions would be used:
        let address = crate::autobahn::Address::new("localhost", 8080);
        let client = crate::autobahn::Autobahn::new_default(address);

        // Initialize server to handle RPC calls
        client.initialize_rpc_server().await;

        println!("RPC server initialized successfully");

        // Give connection a brief moment to install subscriptions
        let _ = client.ping().await;
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let result = client::add_numbers(&client, 1000, MathRequest { a: 5, b: 3 }).await;
        match result {
            Ok(response) => assert_eq!(response.result, 8),
            Err(e) => assert!(false, "Error: {}", e),
        }
    }

    #[tokio::test]
    async fn test_rpc_without_args() {
        let address = crate::autobahn::Address::new("localhost", 8080);
        let client = crate::autobahn::Autobahn::new_default(address);

        client.initialize_rpc_server().await;
        // Ensure connection is up before calling no-arg RPC
        let _ = client.ping().await;
        // Give the hub a brief moment to apply subscriptions
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let result = client::get_status(&client, 1000).await;
        match result {
            Ok(_) => assert!(true),
            Err(e) => assert!(false, "Error: {}", e),
        }
    }

    #[tokio::test]
    async fn test_rpc_with_error() {
        let address = crate::autobahn::Address::new("localhost", 8080);
        let client = crate::autobahn::Autobahn::new_default(address);

        client.initialize_rpc_server().await;

        let result = client::error_out(&client, 1000).await;
        match result {
            Ok(_) => assert!(false),
            Err(e) => assert!(true, "Error: {}", e),
        }
    }

    #[tokio::test]
    async fn time_rpc_call() {
        let address = crate::autobahn::Address::new("localhost", 8080);
        let client = crate::autobahn::Autobahn::new_default(address);

        client.initialize_rpc_server().await;

        // Ensure server subscriptions are installed before timing
        let _ = client.ping().await;
        // Give the hub a brief moment to apply subscriptions
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        let start = std::time::Instant::now();
        let result = client::add_numbers(&client, 1000, MathRequest { a: 5, b: 3 }).await;
        let end = std::time::Instant::now();
        println!("Time taken: {:?}", end.duration_since(start));
        match result {
            Ok(response) => assert_eq!(response.result, 8),
            Err(e) => assert!(false, "Error: {}", e),
        }

        assert!(end.duration_since(start) < std::time::Duration::from_millis(300));
    }
}
