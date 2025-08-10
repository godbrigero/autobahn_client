use std::time::Duration;

use autobahn_client::{
    autobahn::{Address, Autobahn},
    client_function,
};
use tokio::time::{sleep, Instant};

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

#[client_function]
async fn test_function(request: MathRequest) -> MathResponse {
    todo!();
}

#[tokio::main]
pub async fn main() {
    let address = Address::new("localhost", 8080);
    let client = Autobahn::new_default(address);

    client.initialize_rpc_server().await;

    let start = Instant::now();
    let result = test_function(&client, 5000, MathRequest { a: 1, b: 2 }).await;
    let end = Instant::now();
    println!("Result: {:?}", result);
    println!("Time: {:?}", end.duration_since(start));
}
