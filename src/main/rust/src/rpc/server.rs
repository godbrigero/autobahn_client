use futures_util::future::BoxFuture;
use prost::Message;
use std::sync::{Arc, Mutex};

use crate::proto::autobahn::{
    RpcMessageType, RpcRequestMessage, RpcResponseMessage, RpcResponseType,
};

use crate::{autobahn::Autobahn, AUTOBAHN_RPC_OUTPUT_PREFIX};

// Trait for type-erased server functions
trait ServerFunctionTrait: Send + Sync {
    fn call(
        &self,
        payload: Vec<u8>,
    ) -> BoxFuture<'static, Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>>>;
    fn get_topic(&self) -> &str;
}

// Generic implementation that maintains type safety internally
struct ServerFunction<I, O>
where
    I: Message + Default + Send + Sync + 'static,
    O: Message + Default + Send + Sync + 'static,
{
    subscribe_topic: String,
    function: Box<
        dyn Fn(I) -> BoxFuture<'static, Result<O, Box<dyn std::error::Error + Send + Sync>>>
            + Send
            + Sync
            + 'static,
    >,
    _phantom: std::marker::PhantomData<(I, O)>,
}

impl<I, O> ServerFunction<I, O>
where
    I: Message + Default + Send + Sync + 'static,
    O: Message + Default + Send + Sync + 'static,
{
    fn new<F, Fut>(subscribe_topic: String, function: F) -> Self
    where
        F: Fn(I) -> Fut + Send + Sync + 'static,
        Fut: futures_util::Future<Output = Result<O, Box<dyn std::error::Error + Send + Sync>>>
            + Send
            + 'static,
    {
        let function_wrapper = Box::new(move |input: I| {
            Box::pin(function(input))
                as BoxFuture<'static, Result<O, Box<dyn std::error::Error + Send + Sync>>>
        });

        Self {
            subscribe_topic,
            function: function_wrapper,
            _phantom: std::marker::PhantomData,
        }
    }
}

impl<I, O> ServerFunctionTrait for ServerFunction<I, O>
where
    I: Message + Default + Send + Sync + 'static,
    O: Message + Default + Send + Sync + 'static,
{
    fn call(
        &self,
        payload: Vec<u8>,
    ) -> BoxFuture<'static, Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>>> {
        let input = match I::decode(&payload[..]) {
            Ok(msg) => msg,
            Err(e) => {
                return Box::pin(async move {
                    Err(Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
                });
            }
        };

        let future = (self.function)(input);

        Box::pin(async move {
            let output = future.await;
            match output {
                Ok(output) => Ok(output.encode_to_vec()),
                Err(e) => Err(e),
            }
        })
    }

    fn get_topic(&self) -> &str {
        &self.subscribe_topic
    }
}

static SERVER_FUNCTION_REGISTRY: Mutex<Vec<Arc<dyn ServerFunctionTrait>>> = Mutex::new(Vec::new());

pub fn register_server_function<I, O, F, Fut>(subscribe_topic: String, function: F)
where
    I: Message + Default + Send + Sync + 'static,
    O: Message + Default + Send + Sync + 'static,
    F: Fn(I) -> Fut + Send + Sync + 'static,
    Fut: futures_util::Future<Output = Result<O, Box<dyn std::error::Error + Send + Sync>>>
        + Send
        + 'static,
{
    let server_function = ServerFunction::<I, O>::new(subscribe_topic, function);

    if let Ok(mut registry) = SERVER_FUNCTION_REGISTRY.lock() {
        registry.push(Arc::new(server_function));
    }
}

pub async fn initialize_rpc_server(autobahn: &Arc<Autobahn>) {
    let Ok(registry) = SERVER_FUNCTION_REGISTRY.lock() else {
        eprintln!("Failed to acquire lock on server function registry");
        return;
    };

    // Clone the Arc list so we don't hold the lock across awaits
    let functions: Vec<Arc<dyn ServerFunctionTrait>> = registry.clone();
    drop(registry);

    for function in functions.into_iter() {
        let topic = function.get_topic().to_string();
        let function = function.clone();
        let autobahn_clone = autobahn.clone();

        if let Err(e) = autobahn
            .subscribe(&topic, move |payload| {
                let payload_deserialized = match RpcRequestMessage::decode(&payload[..]) {
                    Ok(msg) => Some(msg),
                    Err(_) => None,
                };

                let function = function.clone();
                let autobahn = autobahn_clone.clone();
                async move {
                    if payload_deserialized.is_none() {
                        return;
                    }

                    let payload_deserialized = payload_deserialized.unwrap();

                    let request_id = payload_deserialized.call_id;
                    let payload = payload_deserialized.payload;

                    let output_topic = format!("{}{}", AUTOBAHN_RPC_OUTPUT_PREFIX, request_id);
                    let result = function.call(payload).await;
                    let output = match result {
                        Ok(result) => RpcResponseMessage {
                            message_type: RpcMessageType::RpcResponse as i32,
                            response_type: RpcResponseType::RpcResponseSuccess as i32,
                            call_id: request_id,
                            payload: result,
                        },
                        Err(e) => RpcResponseMessage {
                            message_type: RpcMessageType::RpcResponse as i32,
                            response_type: RpcResponseType::RpcResponseError as i32,
                            call_id: request_id,
                            payload: e.to_string().as_bytes().to_vec(),
                        },
                    };

                    if let Err(publish_err) = autobahn
                        .publish(&output_topic, output.encode_to_vec())
                        .await
                    {
                        eprintln!("Failed to publish RPC response: {:?}", publish_err);
                    } else {
                        println!("Published RPC response to topic: {}", output_topic);
                    }
                }
            })
            .await
        {
            eprintln!("Failed to subscribe to RPC topic '{}': {:?}", topic, e);
        }
    }
}
