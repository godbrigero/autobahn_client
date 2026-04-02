package autobahn.client;

import java.net.URI;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.google.protobuf.ByteString;

import proto.autobahn.Message.AbstractMessage;
import proto.autobahn.Message.HeartbeatMessage;
import proto.autobahn.Message.MessageType;
import proto.autobahn.Message.PublishMessage;
import proto.autobahn.Message.TopicMessage;
import proto.autobahn.Message.UnsubscribeMessage;

public class AutobahnClient {

  private static final Duration RECONNECT_DELAY = Duration.ofMillis(5000);
  private static final Duration MAX_CONNECT_TIME = Duration.ofMillis(500);

  private final Address address;
  private final Map<String, List<NamedCallback>> callbacks;
  private final ScheduledExecutorService reconnectExecutor;
  private final Logger logger;

  private WebSocketClient websocket;
  private boolean isReconnecting;

  public AutobahnClient(Address address) {
    this(
        address,
        new HashMap<>(),
        Executors.newSingleThreadScheduledExecutor(),
        LoggerFactory.getLogger(AutobahnClient.class));
  }

  public AutobahnClient(Address address, Logger loggerClass) {
    this(address, new HashMap<>(), Executors.newSingleThreadScheduledExecutor(), loggerClass);
  }

  public AutobahnClient(
      Address address,
      Map<String, List<NamedCallback>> callbacks,
      ScheduledExecutorService reconnectExecutor,
      Logger loggerClass) {
    this.address = address;
    this.callbacks = callbacks;
    this.reconnectExecutor = reconnectExecutor;
    this.logger = loggerClass;
    this.isReconnecting = false;
  }

  private void scheduleReconnect() {
    if (isReconnecting) {
      return;
    }

    isReconnecting = true;
    reconnectExecutor.schedule(
        this::tryReconnect,
        RECONNECT_DELAY.toMillis(),
        TimeUnit.MILLISECONDS);
  }

  private void tryReconnect() {
    if (websocket != null && !websocket.isClosed()) {
      isReconnecting = false;
      return;
    }

    logger.info("Attempting to reconnect to Autobahn server...");
    begin()
        .thenRun(() -> {
          logger.info("Successfully reconnected to Autobahn server");
          isReconnecting = false;
          // Resubscribe to all topics
          callbacks.forEach((topic, callbacks) -> callbacks.forEach(callback -> subscribe(topic, callback)));
        })
        .exceptionally(ex -> {
          logger.error("Reconnection attempt failed: " + ex.getMessage());
          scheduleReconnect(); // Schedule another attempt
          return null;
        });
  }

  public boolean isConnected() {
    return websocket != null && !websocket.isClosed() && !isReconnecting && !websocket.isClosing()
        && websocket.isOpen();
  }

  public CompletableFuture<Void> begin() {
    return CompletableFuture.runAsync(() -> {
      AtomicBoolean isConnected = new AtomicBoolean(false);
      long startTime = System.currentTimeMillis();
      try {
        websocket = new WebSocketClient(new URI(address.makeUrl())) {
          @Override
          public void onOpen(ServerHandshake handshake) {
            isConnected.set(true);
          }

          @Override
          public void onMessage(String message) {
          }

          @Override
          public void onMessage(ByteBuffer message) {
            byte[] messageBytes = new byte[message.remaining()];
            message.get(messageBytes);
            handleMessage(messageBytes);
          }

          @Override
          public void onClose(int code, String reason, boolean remote) {
            logger.error("WebSocket connection closed: " + reason);
            scheduleReconnect();
          }

          @Override
          public void onError(Exception ex) {
            logger.error("WebSocket error: " + ex.getMessage());
            scheduleReconnect();
          }
        };
        websocket.connect();

        while (!isConnected.get() && System.currentTimeMillis() - startTime < MAX_CONNECT_TIME.toMillis()) {
          try {
            Thread.sleep(10);
          } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
          }
        }

        logger.info("Time taken to connect: " + (System.currentTimeMillis() - startTime) + "ms");
      } catch (Exception e) {
        logger.error("Failed to connect: " + e.getMessage());
        throw new RuntimeException("Failed to connect to WebSocket address");
      }
    });
  }

  public CompletableFuture<Void> publish(String topic, byte[] payload) {
    if (websocket == null || websocket.isClosed()) {
      throw new IllegalStateException(
          "No WebSocket connection available. Call begin() first.");
    }

    return CompletableFuture.runAsync(() -> {
      try {
        PublishMessage message = PublishMessage
            .newBuilder()
            .setMessageType(MessageType.PUBLISH)
            .setTopic(topic)
            .setPayload(ByteString.copyFrom(payload))
            .build();

        websocket.send(message.toByteArray());
      } catch (Exception e) {
        throw new RuntimeException(
            "Failed to publish message: " + e.getMessage());
      }
    });
  }

  public CompletableFuture<Void> subscribe(
      String topic,
      NamedCallback callback) {
    if (websocket == null || websocket.isClosed()) {
      throw new IllegalStateException(
          "No WebSocket connection available. Call begin() first.");
    }

    return CompletableFuture.runAsync(() -> {
      try {
        callbacks.putIfAbsent(topic, new ArrayList<>());
        callbacks.get(topic).add(callback);

        TopicMessage message = TopicMessage
            .newBuilder()
            .setMessageType(MessageType.SUBSCRIBE)
            .setTopic(topic)
            .build();

        websocket.send(message.toByteArray());
      } catch (Exception e) {
        throw new RuntimeException("Failed to subscribe: " + e.getMessage());
      }
    });
  }

  public CompletableFuture<Void> subscribe(
      List<String> topics,
      NamedCallback callback) {
    var allFutures = new ArrayList<CompletableFuture<Void>>();
    for (String topic : topics) {
      allFutures.add(subscribe(topic, callback));
    }

    return CompletableFuture.allOf(
        allFutures.toArray(new CompletableFuture[0]));
  }

  public CompletableFuture<Void> unsubscribe(String topic) {
    if (websocket == null || websocket.isClosed()) {
      throw new IllegalStateException(
          "No WebSocket connection available. Call begin() first.");
    }

    return CompletableFuture.runAsync(() -> {
      try {
        callbacks.remove(topic);

        UnsubscribeMessage message = UnsubscribeMessage
            .newBuilder()
            .setMessageType(MessageType.UNSUBSCRIBE)
            .setTopic(topic)
            .build();

        websocket.send(message.toByteArray());
      } catch (Exception e) {
        throw new RuntimeException("Failed to unsubscribe: " + e.getMessage());
      }
    });
  }

  public CompletableFuture<Void> unsubscribe(
      String topic,
      NamedCallback callback) {
    if (websocket == null || websocket.isClosed()) {
      throw new IllegalStateException(
          "No WebSocket connection available. Call begin() first.");
    }

    return CompletableFuture.runAsync(() -> {
      try {
        callbacks.get(topic).remove(callback);
        if (callbacks.get(topic).isEmpty()) {
          unsubscribe(topic);
        }
      } catch (Exception e) {
        throw new RuntimeException("Failed to unsubscribe: " + e.getMessage());
      }
    });
  }

  private void handleMessage(byte[] messageBytes) {
    AbstractMessage abstractMessage;
    try {
      abstractMessage = AbstractMessage.parseFrom(messageBytes);
    } catch (Exception e) {
      logger.error("Error parsing abstract message: " + e.getMessage());
      return;
    }

    switch (abstractMessage.getMessageType()) {
      case HEARTBEAT:
        // Ignore payload and just respond with a heartbeat message
        sendHeartbeat();
        break;
      case PUBLISH:
        onPublishMessage(messageBytes);
        break;
      default:
        break;
    }
  }

  private void onPublishMessage(byte[] messageBytes) {
    PublishMessage pubMessage;
    try {
      pubMessage = PublishMessage.parseFrom(messageBytes);
    } catch (Exception e) {
      logger.error("Error in message handler: " + e.getMessage());
      return;
    }

    String topic = pubMessage.getTopic();
    callbacks.getOrDefault(topic, new ArrayList<>())
        .forEach(callback -> callback.accept(pubMessage.getPayload().toByteArray()));
  }

  private void sendHeartbeat() {
    if (websocket == null || websocket.isClosed()) {
      throw new IllegalStateException(
          "No WebSocket connection available. Call begin() first.");
    }

    HeartbeatMessage heartbeatMessage = HeartbeatMessage
        .newBuilder()
        .setMessageType(MessageType.HEARTBEAT)
        .addAllTopics(callbacks.keySet())
        .build();

    websocket.send(heartbeatMessage.toByteArray());
  }
}
