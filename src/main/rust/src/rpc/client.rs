use prost::Message;
use std::sync::Arc;
use tokio::sync::oneshot;
use uuid::Uuid;

use crate::{
    proto::autobahn::{RpcMessageType, RpcRequestMessage, RpcResponseMessage, RpcResponseType},
    rpc::RPCError,
    util::deserialize_partial,
};

use crate::{autobahn::Autobahn, AUTOBAHN_RPC_OUTPUT_PREFIX, AUTOBAHN_RPC_PREFIX};

impl Autobahn {
    pub async fn call_rpc<OutputType: prost::Message + Default, ArgsType: prost::Message>(
        self: &Arc<Self>,
        fn_rpc_id: String,
        args: ArgsType,
        timeout_ms: u64,
    ) -> Result<OutputType, RPCError> {
        let input_args_bytes = args.encode_to_vec();

        let call_id = Self::generate_call_id();

        let rpc_request_message = RpcRequestMessage {
            message_type: RpcMessageType::RpcRequest as i32,
            call_id: call_id.clone(),
            payload: input_args_bytes,
        };

        let input_args_topic = self.from_function_id_to_rpc_publish_topic(&fn_rpc_id);

        let subscribe_topic = self.from_function_id_to_rpc_subscribe_topic(&call_id);

        // Prepare a one-shot receiver and subscribe BEFORE publishing to avoid race conditions
        let (tx, rx) = oneshot::channel::<Vec<u8>>();
        let tx_arc = Arc::new(tokio::sync::Mutex::new(Some(tx)));
        let make_cb = |arc: Arc<tokio::sync::Mutex<Option<oneshot::Sender<Vec<u8>>>>>| {
            move |payload: Vec<u8>| {
                let arc = arc.clone();
                async move {
                    if let Some(sender) = arc.lock().await.take() {
                        let _ = sender.send(payload);
                    }
                }
            }
        };
        let subscribe_callback = make_cb(tx_arc.clone());
        if let Err(e) = self.subscribe(&subscribe_topic, subscribe_callback).await {
            return Err(RPCError::ConnectionError(e.to_string()));
        }
        // No extra waits here; Autobahn::subscribe defers subscribe on connect if needed

        let output = self
            .publish(
                input_args_topic.as_str(),
                rpc_request_message.encode_to_vec(),
            )
            .await;

        match output {
            Ok(_) => {}
            Err(e) => {
                return Err(RPCError::ConnectionError(e.to_string()));
            }
        }

        let response = tokio::time::timeout(std::time::Duration::from_millis(timeout_ms), async {
            let bytes = rx
                .await
                .map_err(|e| RPCError::Other(format!("Receive error: {}", e)))?;
            // best-effort cleanup of the per-call topic
            let _ = self.unsubscribe(&subscribe_topic).await;
            RpcResponseMessage::decode(&bytes[..]).map_err(|e| {
                RPCError::DeserializationError(format!("Failed to decode response: {}", e))
            })
        })
        .await;

        if response.is_err() {
            let _ = self.unsubscribe(&subscribe_topic).await;
            return Err(RPCError::TimeoutError(response.err().unwrap().to_string()));
        }

        let response = response.unwrap()?;

        match response.response_type {
            x if x == RpcResponseType::RpcResponseSuccess as i32 => {
                // prost::Message::decode expects something that implements Buf, so use &[u8]
                return deserialize_partial(&*response.payload).map_err(|e| {
                    RPCError::DeserializationError(format!("Failed to decode response: {}", e))
                });
            }
            x if x == RpcResponseType::RpcResponseError as i32 => {
                // Vec<u8> does not implement Display, so use debug formatting
                return Err(RPCError::ErrorResponse(format!(
                    "RPC error response: {:?}",
                    response.payload
                )));
            }
            _ => return Err(RPCError::Other("Unknown response type".to_string())), // should never happen
        }
    }

    /// Generate a call_id as a UUID v4 string, matching Python's `str(uuid.uuid4())`
    fn generate_call_id() -> String {
        Uuid::new_v4().to_string()
    }

    fn from_function_id_to_rpc_subscribe_topic(&self, call_id: &str) -> String {
        format!("{}{}", AUTOBAHN_RPC_OUTPUT_PREFIX, call_id)
    }

    fn from_function_id_to_rpc_publish_topic(&self, fn_rpc_id: &str) -> String {
        format!("{}{}", AUTOBAHN_RPC_PREFIX, fn_rpc_id)
    }

    // Note: we no longer use a polling-based waiter; subscription happens before publish.
}
