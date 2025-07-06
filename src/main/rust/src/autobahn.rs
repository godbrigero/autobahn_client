use futures_util::{SinkExt, StreamExt};
use prost::Message as ProstMessage;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;
use tokio::time;
use tokio_tungstenite::{connect_async, tungstenite::Message as WsMessage};

use crate::proto::autobahn::{MessageType, PublishMessage, TopicMessage};

#[derive(Clone, Debug)]
pub struct Address {
    host: String,
    port: u16,
}

impl Address {
    pub fn new(host: impl Into<String>, port: u16) -> Self {
        Self {
            host: host.into(),
            port,
        }
    }

    pub fn make_url(&self) -> String {
        format!("ws://{}:{}", self.host, self.port)
    }
}

type Callback = Arc<dyn Fn(Vec<u8>) -> futures_util::future::BoxFuture<'static, ()> + Send + Sync>;

pub struct Autobahn {
    address: Address,
    websocket: Arc<
        Mutex<
            Option<
                tokio_tungstenite::WebSocketStream<
                    tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
                >,
            >,
        >,
    >,
    callbacks: Arc<Mutex<HashMap<String, Callback>>>,
    first_subscription: Arc<Mutex<bool>>,
    reconnect: bool,
    reconnect_interval: Duration,
}

impl Autobahn {
    pub fn new(address: Address, reconnect: bool, reconnect_interval_seconds: f64) -> Self {
        Self {
            address,
            websocket: Arc::new(Mutex::new(None)),
            callbacks: Arc::new(Mutex::new(HashMap::new())),
            first_subscription: Arc::new(Mutex::new(true)),
            reconnect,
            reconnect_interval: Duration::from_secs_f64(reconnect_interval_seconds),
        }
    }

    pub fn new_default(address: Address) -> Self {
        Self::new(address, true, 5.0)
    }

    async fn connect(
        &self,
    ) -> Result<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Box<dyn std::error::Error>,
    > {
        let url = self.address.make_url();
        let (ws_stream, _) = connect_async(&url).await?;
        Ok(ws_stream)
    }

    pub async fn begin(&self) -> Result<(), Box<dyn std::error::Error>> {
        match self.connect().await {
            Ok(ws) => {
                *self.websocket.lock().await = Some(ws);
            }
            Err(e) => {
                eprintln!(
                    "Failed to connect to WebSocket at {}: {}",
                    self.address.make_url(),
                    e
                );
            }
        }

        if self.reconnect {
            let websocket = self.websocket.clone();
            let address = self.address.clone();
            let callbacks = self.callbacks.clone();
            let interval = self.reconnect_interval;

            tokio::spawn(async move {
                loop {
                    time::sleep(interval).await;

                    let mut ws_lock = websocket.lock().await;
                    if ws_lock.is_none() {
                        match connect_async(&address.make_url()).await {
                            Ok((ws, _)) => {
                                *ws_lock = Some(ws);

                                // Resubscribe to topics
                                let callbacks = callbacks.lock().await;
                                for topic in callbacks.keys() {
                                    if let Some(ws) = ws_lock.as_mut() {
                                        let msg = TopicMessage {
                                            message_type: MessageType::Subscribe as i32,
                                            topic: topic.clone(),
                                        };
                                        let bytes = msg.encode_to_vec();
                                        let _ = ws.send(WsMessage::Binary(bytes.into())).await;
                                    }
                                }
                            }
                            Err(e) => {
                                eprintln!("Reconnection attempt failed: {}", e);
                            }
                        }
                    } else if let Some(ws) = ws_lock.as_mut() {
                        if let Err(_) = ws.send(WsMessage::Ping(vec![].into())).await {
                            *ws_lock = None;
                            eprintln!("Reconnecting...");
                        }
                    }
                }
            });
        }

        Ok(())
    }

    pub async fn ping(&self) -> Result<(), Box<dyn std::error::Error>> {
        let ws_lock = self.websocket.lock().await;
        if let Some(ws) = ws_lock.as_ref() {
            Ok(())
        } else {
            Err("WebSocket not connected. Call begin() first.".into())
        }
    }

    pub async fn publish(
        &self,
        topic: &str,
        payload: Vec<u8>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        if !self.reconnect {
            let ws_lock = self.websocket.lock().await;
            if ws_lock.is_none() {
                return Err("WebSocket not connected. Call begin() first.".into());
            }
        }

        let mut ws_lock = self.websocket.lock().await;
        if let Some(ws) = ws_lock.as_mut() {
            let msg = PublishMessage {
                message_type: MessageType::Publish as i32,
                topic: topic.to_string(),
                payload,
            };
            let bytes = msg.encode_to_vec();
            ws.send(WsMessage::Binary(bytes.into())).await?;
        }

        Ok(())
    }

    pub async fn subscribe<F, Fut>(
        &self,
        topic: &str,
        callback: F,
    ) -> Result<(), Box<dyn std::error::Error>>
    where
        F: Fn(Vec<u8>) -> Fut + Send + Sync + 'static,
        Fut: futures_util::Future<Output = ()> + Send + 'static,
    {
        if !self.reconnect {
            let ws_lock = self.websocket.lock().await;
            if ws_lock.is_none() {
                return Err("WebSocket not connected. Call begin() first.".into());
            }
        }

        // Store callback
        let callback = Arc::new(move |payload: Vec<u8>| {
            Box::pin(callback(payload)) as futures_util::future::BoxFuture<'static, ()>
        });
        self.callbacks
            .lock()
            .await
            .insert(topic.to_string(), callback);

        // Send subscription message
        if let Some(ws) = self.websocket.lock().await.as_mut() {
            let msg = TopicMessage {
                message_type: MessageType::Subscribe as i32,
                topic: topic.to_string(),
            };
            let bytes = msg.encode_to_vec();
            ws.send(WsMessage::Binary(bytes.into())).await?;
        }

        // Start listener if this is the first subscription
        let mut first_sub = self.first_subscription.lock().await;
        if *first_sub {
            *first_sub = false;
            let websocket = self.websocket.clone();
            let callbacks = self.callbacks.clone();

            tokio::spawn(async move {
                loop {
                    time::sleep(Duration::from_millis(100)).await;

                    let mut ws_lock = websocket.lock().await;
                    if let Some(ws) = ws_lock.as_mut() {
                        match ws.next().await {
                            Some(Ok(WsMessage::Binary(msg))) => {
                                if let Ok(publish_msg) = PublishMessage::decode(&msg[..]) {
                                    if publish_msg.message_type == MessageType::Publish as i32 {
                                        let callbacks = callbacks.lock().await;
                                        if let Some(callback) = callbacks.get(&publish_msg.topic) {
                                            let callback = callback.clone();
                                            let payload = publish_msg.payload;
                                            tokio::spawn(async move {
                                                callback(payload).await;
                                            });
                                        }
                                    }
                                }
                            }
                            Some(Ok(WsMessage::Close(_))) | None => {
                                *ws_lock = None;
                                eprintln!(
                                    "WebSocket connection closed, waiting for reconnection..."
                                );
                            }
                            Some(Err(e)) => {
                                eprintln!("Error in listener: {}", e);
                                *ws_lock = None;
                            }
                            _ => {}
                        }
                    }
                }
            });
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_autobahn() {
        let messages = Arc::new(Mutex::new(Vec::new()));
        let autobahn = Autobahn::new_default(Address::new("localhost", 8080));
        autobahn.begin().await.unwrap();

        let messages_clone = messages.clone();
        autobahn
            .subscribe("test", move |payload| {
                let messages_clone = messages_clone.clone();

                async move {
                    let mut messages = messages_clone.lock().await;
                    messages.push(payload);
                }
            })
            .await
            .unwrap();

        autobahn
            .publish("test", b"Hello, world!".to_vec())
            .await
            .unwrap();

        time::sleep(Duration::from_millis(500)).await;

        assert_eq!(messages.lock().await.len(), 1);
        assert_eq!(messages.lock().await[0], b"Hello, world!");
    }
}
