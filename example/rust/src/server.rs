use autobahn_client::{
    autobahn::{Address, Autobahn},
    proto::autobahn::{AbstractMessage, MessageType, ServerForwardMessage},
    server_function,
};
use tokio::signal;

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

#[server_function]
async fn test_function(request: MathRequest) -> MathResponse {
    MathResponse {
        result: request.a + request.b,
    }
}

#[server_function]
async fn get_user(_request: AbstractMessage) -> ServerForwardMessage {
    ServerForwardMessage {
        message_type: MessageType::ServerForward as i32,
        payload: b"Hello, world!".to_vec(),
    }
}

#[tokio::main]
pub async fn main() {
    let address = Address::new("localhost", 8080);
    let client = Autobahn::new_default(address);

    client.initialize_rpc_server().await;

    // Keep the server running until interrupted
    let _ = signal::ctrl_c().await;
}
