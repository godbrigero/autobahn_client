package autobahn.client;

import java.net.URI;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.google.protobuf.ByteString;

import proto.autobahn.Message.MessageType;
import proto.autobahn.Message.PublishMessage;
import proto.autobahn.Message.PublishMessageOrBuilder;
import proto.autobahn.Message.TopicMessage;
import proto.autobahn.Message.UnsubscribeMessage;

public class AutobahnClient {

  private final Address address;
  private WebSocketClient websocket;
  private final Map<String, List<NamedCallback>> callbacks;
  private final ScheduledExecutorService reconnectExecutor;
  private boolean isReconnecting = false;
  private static final int RECONNECT_DELAY_MS = 5000;
  private final Logger logger;

  public AutobahnClient(Address address) {
    this(
        address,
        new HashMap<>(),
        Executors.newSingleThreadScheduledExecutor());
  }

  public AutobahnClient(
      Address address,
      Map<String, List<NamedCallback>> callbacks,
      ScheduledExecutorService reconnectExecutor) {
    this.address = address;
    this.callbacks = callbacks;
    this.reconnectExecutor = reconnectExecutor;
    this.logger = LoggerFactory.getLogger(AutobahnClient.class);
  }

  private void scheduleReconnect() {
    if (isReconnecting) {
      return;
    }

    isReconnecting = true;
    reconnectExecutor.schedule(
        this::tryReconnect,
        RECONNECT_DELAY_MS,
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

  public CompletableFuture<Void> begin() {
    return CompletableFuture.runAsync(() -> {
      try {
        websocket = new WebSocketClient(new URI(address.makeUrl())) {
          @Override
          public void onOpen(ServerHandshake handshake) {
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
    try {
      PublishMessageOrBuilder messageProto = proto.autobahn.Message.PublishMessage.parseFrom(
          messageBytes);

      if (messageProto.getMessageType() == MessageType.PUBLISH) {
        String topic = messageProto.getTopic();
        if (callbacks.containsKey(topic)) {
          callbacks
              .get(topic)
              .forEach(callback -> callback.accept(messageProto.getPayload().toByteArray()));
        }
      }
    } catch (Exception e) {
      logger.error("Error in message handler: " + e.getMessage());
    }
  }
}
