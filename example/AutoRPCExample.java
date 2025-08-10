package example;

import autobahn.client.rpc.AutobahnRPC;
import autobahn.client.rpc.client.ClientFunction;
import autobahn.client.rpc.server.ServerFunction;

// Import your protobuf message types here
// import your.proto.messages.RequestMessage;
// import your.proto.messages.ResponseMessage;

/**
 * Example demonstrating the new automatic RPC client generation.
 * Users only need to define method signatures - implementations are generated automatically!
 */

// ===== CLIENT INTERFACE =====
// Define your RPC client methods as an interface
public interface MyRPCClient {
  /**
   * This method signature gets automatic implementation!
   * No need to write the RPC call logic manually.
   */
  @ClientFunction(timeoutMs = 5000)
  ResponseMessage processData(RequestMessage request);

  /**
   * Example of a void method call
   */
  @ClientFunction(timeoutMs = 3000)
  void triggerAction();

  /**
   * Example with no parameters
   */
  @ClientFunction(timeoutMs = 2000)
  ResponseMessage getStatus();
}

// ===== SERVER IMPLEMENTATION =====
// Server functions still work the same way as before
public class MyRPCServer {

  @ServerFunction
  public static ResponseMessage processData(RequestMessage request) {
    // Your server logic here
    return ResponseMessage
      .newBuilder()
      .setResult("Processed: " + request.getData())
      .build();
  }

  @ServerFunction
  public static void triggerAction() {
    System.out.println("Action triggered remotely!");
  }

  @ServerFunction
  public static ResponseMessage getStatus() {
    return ResponseMessage.newBuilder().setResult("Server is running").build();
  }
}

// ===== USAGE EXAMPLE =====
class RPCUsageExample {

  public static void main(String[] args) throws Exception {
    // 1. Set up AutobahnClient (you need to provide your client instance)
    // AutobahnRPC.setAutobahnClient(yourAutobahnClientInstance);

    // 2. Register server functions (if this instance serves RPC calls)
    AutobahnRPC.registerRPCServices(MyRPCServer.class);

    // 3. Create automatic client implementation
    MyRPCClient client = AutobahnRPC.createRPCClient(MyRPCClient.class);

    // 4. Use the client - all method calls are automatically converted to RPC calls!
    try {
      // Call with parameter
      RequestMessage request = RequestMessage
        .newBuilder()
        .setData("Hello World")
        .build();
      ResponseMessage response = client.processData(request);
      System.out.println("Response: " + response.getResult());

      // Call with no return value
      client.triggerAction();

      // Call with no parameters
      ResponseMessage status = client.getStatus();
      System.out.println("Status: " + status.getResult());
    } catch (Exception e) {
      System.err.println("RPC call failed: " + e.getMessage());
    }
  }
}
/*
 * HOW IT WORKS:
 *
 * 1. You define an interface with @ClientFunction annotated methods
 * 2. Call AutobahnRPC.createRPCClient(YourInterface.class)
 * 3. The system automatically generates a proxy implementation that:
 *    - Validates method signatures
 *    - Converts parameters to protobuf messages
 *    - Publishes RPC requests with unique call IDs
 *    - Waits for responses with timeout handling
 *    - Converts responses back to return types
 *    - Handles errors and timeouts
 *
 * BENEFITS:
 * - No boilerplate RPC call code
 * - Type-safe method signatures
 * - Automatic timeout handling
 * - Clean separation of interface and implementation
 * - Easy to mock for testing
 *
 * REQUIREMENTS:
 * - Interface methods must be annotated with @ClientFunction
 * - Parameters must be protobuf messages or void
 * - Return types must be protobuf messages or void
 * - AutobahnClient must be set before creating clients
 */
