use futures_util::stream::SplitSink;
use futures_util::{SinkExt, StreamExt};
use prost::Message as ProstMessage;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{watch, Mutex};
use tokio::time;
use tokio_tungstenite::{connect_async, tungstenite::Message as WsMessage};

use crate::{
    proto::autobahn::{MessageType, PublishMessage, TopicMessage},
    rpc::server::initialize_rpc_server,
};

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
    write: Arc<
        Mutex<
            Option<
                SplitSink<
                    tokio_tungstenite::WebSocketStream<
                        tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
                    >,
                    WsMessage,
                >,
            >,
        >,
    >,
    callbacks: Arc<Mutex<HashMap<String, Callback>>>,
    reconnect: bool,
    reconnect_interval: Duration,
    // Ensures we only start the connection/reconnect task once
    started: Arc<Mutex<bool>>,
    connection_tx: watch::Sender<bool>,
}

impl Autobahn {
    pub fn new(address: Address, reconnect: bool, reconnect_interval_seconds: f64) -> Arc<Self> {
        let (connection_tx, _rx) = watch::channel(false);

        Arc::new(Self {
            address,
            write: Arc::new(Mutex::new(None)),
            callbacks: Arc::new(Mutex::new(HashMap::new())),
            reconnect,
            reconnect_interval: Duration::from_secs_f64(reconnect_interval_seconds),
            started: Arc::new(Mutex::new(false)),
            connection_tx,
        })
    }

    pub fn new_default(address: Address) -> Arc<Self> {
        Self::new(address, true, 5.0)
    }

    async fn connect(
        self: Arc<Self>,
    ) -> Result<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Box<dyn std::error::Error>,
    > {
        let url = self.address.make_url();
        let (mut ws_stream, _) = connect_async(&url).await?;
        // Disable Nagle when we're on plain TCP to avoid delayed ACK (~200ms)
        if let tokio_tungstenite::MaybeTlsStream::Plain(tcp) = ws_stream.get_mut() {
            tcp.set_nodelay(true)?;
        }
        Ok(ws_stream)
    }

    pub async fn begin(self: &Arc<Self>) -> Result<(), Box<dyn std::error::Error>> {
        // Guard against multiple starts
        {
            let mut started = self.started.lock().await;
            if !*started {
                match self.clone().connect().await {
                    Ok(ws) => {
                        let (mut write, mut read) = ws.split();
                        // Resubscribe to any existing topics immediately after connecting
                        {
                            let callbacks_guard = self.callbacks.lock().await;
                            for topic in callbacks_guard.keys() {
                                let msg = TopicMessage {
                                    message_type: MessageType::Subscribe as i32,
                                    topic: topic.clone(),
                                };
                                let bytes = msg.encode_to_vec();
                                let _ = write.send(WsMessage::Binary(bytes.into())).await;
                            }
                        }

                        *self.write.lock().await = Some(write);
                        let _ = self.connection_tx.send(true);

                        let callbacks = self.callbacks.clone();
                        tokio::spawn(async move {
                            while let Some(msg) = read.next().await {
                                if let Ok(WsMessage::Binary(msg)) = msg {
                                    if let Ok(publish_msg) = PublishMessage::decode(&msg[..]) {
                                        if publish_msg.message_type == MessageType::Publish as i32 {
                                            let callbacks = callbacks.lock().await;
                                            if let Some(callback) =
                                                callbacks.get(&publish_msg.topic)
                                            {
                                                let callback = callback.clone();
                                                let payload = publish_msg.payload;
                                                tokio::spawn(async move {
                                                    callback(payload).await;
                                                });
                                            }
                                        }
                                    }
                                }
                            }
                        });
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
                    let write_arc = self.write.clone();
                    let address = self.address.clone();
                    let callbacks = self.callbacks.clone();
                    let interval = self.reconnect_interval;
                    let connection_tx = self.connection_tx.clone();

                    tokio::spawn(async move {
                        loop {
                            time::sleep(interval).await;

                            let mut write_lock = write_arc.lock().await;
                            if write_lock.is_none() {
                                match connect_async(&address.make_url()).await {
                                    Ok((ws, _)) => {
                                        let (mut write, mut read) = ws.split();
                                        // Resubscribe to topics using the new writer
                                        {
                                            let callbacks_guard = callbacks.lock().await;
                                            for topic in callbacks_guard.keys() {
                                                let msg = TopicMessage {
                                                    message_type: MessageType::Subscribe as i32,
                                                    topic: topic.clone(),
                                                };
                                                let bytes = msg.encode_to_vec();
                                                let _ = write
                                                    .send(WsMessage::Binary(bytes.into()))
                                                    .await;
                                            }
                                        }

                                        // Store the writer after successful resubscription
                                        *write_lock = Some(write);
                                        let _ = connection_tx.send(true);

                                        // Spawn reader for the new connection
                                        let callbacks_for_reader = callbacks.clone();
                                        tokio::spawn(async move {
                                            while let Some(msg) = read.next().await {
                                                if let Ok(WsMessage::Binary(msg)) = msg {
                                                    if let Ok(publish_msg) =
                                                        PublishMessage::decode(&msg[..])
                                                    {
                                                        if publish_msg.message_type
                                                            == MessageType::Publish as i32
                                                        {
                                                            let callbacks =
                                                                callbacks_for_reader.lock().await;
                                                            if let Some(callback) =
                                                                callbacks.get(&publish_msg.topic)
                                                            {
                                                                let callback = callback.clone();
                                                                let payload = publish_msg.payload;
                                                                tokio::spawn(async move {
                                                                    callback(payload).await;
                                                                });
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        });
                                    }
                                    Err(e) => {
                                        eprintln!("Reconnection attempt failed: {}", e);
                                    }
                                }
                            } else if let Some(writer) = write_lock.as_mut() {
                                if let Err(_) = writer.send(WsMessage::Ping(vec![].into())).await {
                                    *write_lock = None;
                                    eprintln!("Reconnecting...");
                                }
                            }
                        }
                    });
                }

                *started = true;
            }
        }

        Ok(())
    }

    pub async fn ping(self: &Arc<Self>) -> Result<(), Box<dyn std::error::Error>> {
        let write_lock = self.write.lock().await;
        if let Some(_ws) = write_lock.as_ref() {
            Ok(())
        } else {
            Err("WebSocket not connected. Call begin() first.".into())
        }
    }

    pub(crate) async fn wait_until_connected(&self) {
        let mut rx = self.connection_tx.subscribe();
        loop {
            if *rx.borrow() {
                return;
            }
            if rx.changed().await.is_err() {
                // sender dropped, treat as disconnected and retry
                continue;
            }
        }
    }

    pub async fn publish(
        self: &Arc<Self>,
        topic: &str,
        payload: Vec<u8>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let mut write_lock = self.write.lock().await;
        if let Some(writer) = write_lock.as_mut() {
            let msg = PublishMessage {
                message_type: MessageType::Publish as i32,
                topic: topic.to_string(),
                payload,
            };
            let bytes = msg.encode_to_vec();
            writer.send(WsMessage::Binary(bytes.into())).await?;
        } else {
            return Err("WebSocket not connected.".into());
        }

        Ok(())
    }

    pub async fn unsubscribe(
        self: &Arc<Self>,
        topic: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        // First remove the callback to prevent new messages from being processed
        self.callbacks.lock().await.remove(topic);

        // Then try to send the unsubscribe message directly if connected
        let write_arc = self.write.clone();
        let topic = topic.to_string();

        let mut write_lock = write_arc.lock().await;
        if let Some(writer) = write_lock.as_mut() {
            let msg = TopicMessage {
                message_type: MessageType::Unsubscribe as i32,
                topic: topic.clone(),
            };
            let bytes = msg.encode_to_vec();
            writer.send(WsMessage::Binary(bytes.into())).await?;
        }
        Ok(())
    }

    pub async fn subscribe<F, Fut>(
        self: &Arc<Self>,
        topic: &str,
        callback: F,
    ) -> Result<(), Box<dyn std::error::Error>>
    where
        F: Fn(Vec<u8>) -> Fut + Send + Sync + 'static,
        Fut: futures_util::Future<Output = ()> + Send + 'static,
    {
        // Try to send immediately if connected; otherwise rely on auto-resubscribe on connect

        // Store callback
        let callback = Arc::new(move |payload: Vec<u8>| {
            Box::pin(callback(payload)) as futures_util::future::BoxFuture<'static, ()>
        });
        self.callbacks
            .lock()
            .await
            .insert(topic.to_string(), callback);

        // Send subscription message now if connected
        if let Some(writer) = self.write.lock().await.as_mut() {
            let msg = TopicMessage {
                message_type: MessageType::Subscribe as i32,
                topic: topic.to_string(),
            };
            let bytes = msg.encode_to_vec();
            writer.send(WsMessage::Binary(bytes.into())).await?;
        } else {
            // If not connected yet, schedule a deferred subscribe for when we connect
            let topic_string = topic.to_string();
            let write_arc = self.write.clone();
            let mut rx = self.connection_tx.subscribe();
            tokio::spawn(async move {
                // wait for connection signal
                loop {
                    if *rx.borrow() {
                        break;
                    }
                    if rx.changed().await.is_err() {
                        // sender dropped; retry loop
                        continue;
                    }
                }
                // send subscribe once writer is available
                let mut guard = write_arc.lock().await;
                if let Some(writer) = guard.as_mut() {
                    let msg = TopicMessage {
                        message_type: MessageType::Subscribe as i32,
                        topic: topic_string,
                    };
                    let bytes = msg.encode_to_vec();
                    let _ = writer.send(WsMessage::Binary(bytes.into())).await;
                }
            });
        }

        Ok(())
    }

    /// Initialize the RPC server by registering all server functions
    /// This should be called after connecting to start handling RPC requests
    pub async fn initialize_rpc_server(self: &Arc<Self>) {
        // Ensure we are connected and the background tasks are running
        let _ = self.begin().await;
        // Best-effort: wait briefly for an active connection to minimize races
        let _ = tokio::time::timeout(Duration::from_millis(500), self.wait_until_connected()).await;
        // The actual implementation is in server.rs
        crate::rpc::server::initialize_rpc_server(self).await;
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
