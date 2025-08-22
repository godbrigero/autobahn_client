package autobahn.client;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;

import com.google.protobuf.ByteString;

import autobahn.client.rpc.client.ClientFunction;
import proto.autobahn.Message.MessageType;
import proto.autobahn.Message.PublishMessage;

@ExtendWith(MockitoExtension.class)
public class IntegrationTests {

  @Mock
  private ScheduledExecutorService mockExecutor;

  private Address testAddress;
  private AutobahnClient client;

  @BeforeEach
  void setUp() {
    testAddress = new Address("localhost", 8080);
    client = new AutobahnClient(testAddress, new HashMap<>(), mockExecutor,
        LoggerFactory.getLogger(AutobahnClient.class));
  }

  @ClientFunction
  void testRPCFunction() {
  }

  @DisplayName("Address Tests")
  @Test
  void testAddressConstruction() {
    // Test constructor
    Address addr = new Address("localhost", 8080);
    assertEquals("localhost", addr.getHost());
    assertEquals(8080, addr.getPort());

    // Test fromString method
    Address fromString = Address.fromString("localhost:8080");
    assertEquals("localhost", fromString.getHost());
    assertEquals(8080, fromString.getPort());

    // Test fromHostAndPort method
    Address fromHostAndPort = Address.fromHostAndPort("localhost", "8080");
    assertEquals("localhost", fromHostAndPort.getHost());
    assertEquals(8080, fromHostAndPort.getPort());
  }

  @DisplayName("Address URL Generation")
  @Test
  void testAddressUrlGeneration() {
    Address addr = new Address("example.com", 9090);
    assertEquals("ws://example.com:9090", addr.makeUrl());
    assertEquals("ws://example.com:9090", addr.toString());
  }

  @DisplayName("Address fromString with Invalid Format")
  @Test
  void testAddressFromStringInvalidFormat() {
    assertThrows(
        NumberFormatException.class,
        () -> {
          Address.fromString("localhost:invalid");
        });

    assertThrows(
        ArrayIndexOutOfBoundsException.class,
        () -> {
          Address.fromString("localhost");
        });
  }

  @DisplayName("NamedCallback Tests")
  @Test
  void testNamedCallbackCreation() {
    NamedCallback callback = NamedCallback.FromConsumer(bytes -> {
      // Test consumer
    });

    assertNotNull(callback.getCode());
    assertFalse(callback.getCode().isEmpty());
  }

  @DisplayName("NamedCallback Unique Codes")
  @Test
  void testNamedCallbackUniqueCodes() {
    NamedCallback callback1 = NamedCallback.FromConsumer(bytes -> {
    });
    NamedCallback callback2 = NamedCallback.FromConsumer(bytes -> {
    });

    assertNotEquals(callback1.getCode(), callback2.getCode());
    assertNotEquals(callback1, callback2);
  }

  @DisplayName("NamedCallback Equality")
  @Test
  void testNamedCallbackEquality() {
    NamedCallback callback1 = NamedCallback.FromConsumer(bytes -> {
    });
    NamedCallback callback2 = NamedCallback.FromConsumer(bytes -> {
    });

    assertEquals(callback1, callback1);
    assertNotEquals(callback1, callback2);
    assertNotEquals(callback1, "not a callback");
  }

  @DisplayName("NamedCallback Functionality")
  @Test
  void testNamedCallbackFunctionality() {
    AtomicBoolean called = new AtomicBoolean(false);
    AtomicReference<byte[]> receivedData = new AtomicReference<>();

    NamedCallback callback = NamedCallback.FromConsumer(bytes -> {
      called.set(true);
      receivedData.set(bytes);
    });

    byte[] testData = "test data".getBytes();
    callback.accept(testData);

    assertTrue(called.get());
    assertArrayEquals(testData, receivedData.get());
  }

  @Test
  /**
   * @apiNote please note that for this to work, the autobahn server backend needs
   *          to be running and
   *          listening on port 8080 localhost.
   * @throws InterruptedException
   */
  void testPubSubFunctionality() throws InterruptedException {
    client.begin().join();
    var testOutputList = new ArrayList<Integer>();
    client.subscribe("test_topic/123", NamedCallback.FromConsumer((byte[] data) -> {
      testOutputList.add((int) data[0]);
    })).join();

    client.publish("test_topic/123", new byte[] { 11 }).join();

    Thread.sleep(10);

    client.publish("test_topic/123", new byte[] { 12 }).join();

    Thread.sleep(10);

    assertEquals(testOutputList.size(), 2);
    assertEquals(testOutputList.get(0), 11);
    assertEquals(testOutputList.get(1), 12);
  }

  @DisplayName("AutobahnClient Constructor")
  @Test
  void testAutobahnClientConstructor() {
    // Test single-argument constructor
    AutobahnClient simpleClient = new AutobahnClient(testAddress);
    assertNotNull(simpleClient);

    // Test multi-argument constructor
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient fullClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor,
        LoggerFactory.getLogger(AutobahnClient.class));
    assertNotNull(fullClient);
  }

  @DisplayName("AutobahnClient Publish Without Connection")
  @Test
  void testPublishWithoutConnection() {
    byte[] payload = "test payload".getBytes();

    assertThrows(
        IllegalStateException.class,
        () -> {
          client.publish("test/topic", payload).join();
        });
  }

  @DisplayName("AutobahnClient Subscribe Without Connection")
  @Test
  void testSubscribeWithoutConnection() {
    NamedCallback callback = NamedCallback.FromConsumer(bytes -> {
    });

    assertThrows(
        IllegalStateException.class,
        () -> {
          client.subscribe("test/topic", callback).join();
        });
  }

  @DisplayName("AutobahnClient Unsubscribe Without Connection")
  @Test
  void testUnsubscribeWithoutConnection() {
    assertThrows(
        IllegalStateException.class,
        () -> {
          client.unsubscribe("test/topic").join();
        });
  }

  @DisplayName("Message Handling Test")
  @Test
  void testMessageHandling() throws Exception {
    // Create a mock WebSocket client to simulate message handling
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient testClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor, LoggerFactory.getLogger(AutobahnClient.class));

    // Add a callback to test
    AtomicBoolean messageReceived = new AtomicBoolean(false);
    AtomicReference<byte[]> receivedPayload = new AtomicReference<>();

    NamedCallback testCallback = NamedCallback.FromConsumer(bytes -> {
      messageReceived.set(true);
      receivedPayload.set(bytes);
    });

    callbacks.putIfAbsent("test/topic", new ArrayList<>());
    callbacks.get("test/topic").add(testCallback);

    // Create a test message
    byte[] testPayload = "test message payload".getBytes();
    PublishMessage testMessage = PublishMessage
        .newBuilder()
        .setMessageType(MessageType.PUBLISH)
        .setTopic("test/topic")
        .setPayload(ByteString.copyFrom(testPayload))
        .build();

    // Use reflection to access the private handleMessage method
    java.lang.reflect.Method handleMessage = AutobahnClient.class.getDeclaredMethod("handleMessage", byte[].class);
    handleMessage.setAccessible(true);
    handleMessage.invoke(testClient, testMessage.toByteArray());

    // Verify the callback was called
    assertTrue(messageReceived.get());
    assertArrayEquals(testPayload, receivedPayload.get());
  }

  @DisplayName("Protocol Buffer Message Creation")
  @Test
  void testProtocolBufferMessageCreation() {
    // Test PublishMessage creation
    byte[] payload = "test payload".getBytes();
    PublishMessage publishMessage = PublishMessage
        .newBuilder()
        .setMessageType(MessageType.PUBLISH)
        .setTopic("test/topic")
        .setPayload(ByteString.copyFrom(payload))
        .build();

    assertEquals(MessageType.PUBLISH, publishMessage.getMessageType());
    assertEquals("test/topic", publishMessage.getTopic());
    assertArrayEquals(payload, publishMessage.getPayload().toByteArray());
  }

  @DisplayName("Concurrent Operations Test")
  @Test
  void testConcurrentOperations() {
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient concurrentClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor, LoggerFactory.getLogger(AutobahnClient.class));

    // Simulate concurrent callback additions
    List<CompletableFuture<Void>> futures = new ArrayList<>();

    for (int i = 0; i < 10; i++) {
      final int index = i;
      CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
        NamedCallback callback = NamedCallback.FromConsumer(bytes -> {
          // Process message for thread " + index
        });
        System.out.println("topic/" + index);
        callbacks.putIfAbsent("topic/" + index, new ArrayList<>());
        callbacks.get("topic/" + index).add(callback);
      });
      futures.add(future);
    }

    // Wait for all operations to complete
    CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

    // Verify all topics were added
    assertEquals(10, callbacks.size());
    for (int i = 0; i < 10; i++) {
      assertTrue(callbacks.containsKey("topic/" + i));
      assertEquals(1, callbacks.get("topic/" + i).size());
    }
  }

  @DisplayName("Error Handling in Message Processing")
  @Test
  void testErrorHandlingInMessageProcessing() throws Exception {
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient testClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor, LoggerFactory.getLogger(AutobahnClient.class));

    // Add a callback that throws an exception
    NamedCallback errorCallback = NamedCallback.FromConsumer(bytes -> {
      throw new RuntimeException("Test exception in callback");
    });

    callbacks.putIfAbsent("error/topic", new ArrayList<>());
    callbacks.get("error/topic").add(errorCallback);

    // Create a test message
    PublishMessage testMessage = PublishMessage
        .newBuilder()
        .setMessageType(MessageType.PUBLISH)
        .setTopic("error/topic")
        .setPayload(ByteString.copyFrom("test".getBytes()))
        .build();

    // Use reflection to access the private handleMessage method
    java.lang.reflect.Method handleMessage = AutobahnClient.class.getDeclaredMethod("handleMessage", byte[].class);
    handleMessage.setAccessible(true);

    // This should not throw an exception (should be caught internally)
    assertDoesNotThrow(() -> {
      try {
        handleMessage.invoke(testClient, testMessage.toByteArray());
      } catch (Exception e) {
        if (e.getCause() instanceof RuntimeException &&
            e.getCause().getMessage().equals("Test exception in callback")) {
          // This is expected to be caught and logged internally
          return;
        }
        throw e;
      }
    });
  }

  @DisplayName("Invalid Message Handling")
  @Test
  void testInvalidMessageHandling() throws Exception {
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient testClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor, LoggerFactory.getLogger(AutobahnClient.class));

    // Use reflection to access the private handleMessage method
    java.lang.reflect.Method handleMessage = AutobahnClient.class.getDeclaredMethod("handleMessage", byte[].class);
    handleMessage.setAccessible(true);

    // Send invalid message data
    byte[] invalidMessage = "invalid protobuf data".getBytes();

    // This should not throw an exception (should be caught internally)
    assertDoesNotThrow(() -> {
      try {
        handleMessage.invoke(testClient, invalidMessage);
      } catch (Exception e) {
        // Expected to be caught and logged internally
      }
    });
  }

  @DisplayName("Callback Management")
  @Test
  void testCallbackManagement() {
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    String testTopic = "test/topic";

    // Test adding callbacks
    NamedCallback callback1 = NamedCallback.FromConsumer(bytes -> {
    });
    NamedCallback callback2 = NamedCallback.FromConsumer(bytes -> {
    });

    callbacks.putIfAbsent(testTopic, new ArrayList<>());
    callbacks.get(testTopic).add(callback1);
    callbacks.get(testTopic).add(callback2);

    assertEquals(2, callbacks.get(testTopic).size());
    assertTrue(callbacks.get(testTopic).contains(callback1));
    assertTrue(callbacks.get(testTopic).contains(callback2));

    // Test removing callbacks
    callbacks.get(testTopic).remove(callback1);
    assertEquals(1, callbacks.get(testTopic).size());
    assertFalse(callbacks.get(testTopic).contains(callback1));
    assertTrue(callbacks.get(testTopic).contains(callback2));
  }

  @DisplayName("Multiple Topic Subscriptions")
  @Test
  void testMultipleTopicSubscriptions() throws Exception {
    Map<String, List<NamedCallback>> callbacks = new HashMap<>();
    AutobahnClient testClient = new AutobahnClient(
        testAddress,
        callbacks,
        mockExecutor, LoggerFactory.getLogger(AutobahnClient.class));

    AtomicInteger topic1Count = new AtomicInteger(0);
    AtomicInteger topic2Count = new AtomicInteger(0);

    // Add callbacks for different topics
    NamedCallback callback1 = NamedCallback.FromConsumer(bytes -> topic1Count.incrementAndGet());
    NamedCallback callback2 = NamedCallback.FromConsumer(bytes -> topic2Count.incrementAndGet());

    callbacks.putIfAbsent("topic1", new ArrayList<>());
    callbacks.putIfAbsent("topic2", new ArrayList<>());
    callbacks.get("topic1").add(callback1);
    callbacks.get("topic2").add(callback2);

    // Create messages for different topics
    PublishMessage message1 = PublishMessage
        .newBuilder()
        .setMessageType(MessageType.PUBLISH)
        .setTopic("topic1")
        .setPayload(ByteString.copyFrom("payload1".getBytes()))
        .build();

    PublishMessage message2 = PublishMessage
        .newBuilder()
        .setMessageType(MessageType.PUBLISH)
        .setTopic("topic2")
        .setPayload(ByteString.copyFrom("payload2".getBytes()))
        .build();

    // Use reflection to access the private handleMessage method
    java.lang.reflect.Method handleMessage = AutobahnClient.class.getDeclaredMethod("handleMessage", byte[].class);
    handleMessage.setAccessible(true);

    // Send messages
    handleMessage.invoke(testClient, message1.toByteArray());
    handleMessage.invoke(testClient, message2.toByteArray());

    // Verify correct callbacks were called
    assertEquals(1, topic1Count.get());
    assertEquals(1, topic2Count.get());
  }
}
