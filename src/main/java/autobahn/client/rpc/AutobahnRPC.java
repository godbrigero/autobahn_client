package autobahn.client.rpc;

import autobahn.client.AutobahnClient;
import autobahn.client.NamedCallback;
import autobahn.client.rpc.client.ClientFunction;
import autobahn.client.rpc.client.ClientInfo;
import autobahn.client.rpc.server.ServerFunction;
import autobahn.client.rpc.server.ServerFunctionInfo;
import com.google.protobuf.ByteString;
import com.google.protobuf.GeneratedMessageV3;
import com.google.protobuf.InvalidProtocolBufferException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.stream.Stream;
import lombok.Getter;
import proto.autobahn.Message.RPCMessageType;
import proto.autobahn.Message.RPCRequestMessage;
import proto.autobahn.Message.RPCResponseMessage;
import proto.autobahn.Message.RPCResponseType;

public abstract class AutobahnRPC {

  @Getter
  private static class FunctionInfo {

    private Object serviceClass;
    private Map<String, ServerFunctionInfo> serverMethods;
    private Map<String, ClientInfo> clientMethods;

    public FunctionInfo(Object serviceClass) {
      this.serviceClass = serviceClass;
      this.serverMethods = new ConcurrentHashMap<>();
      this.clientMethods = new ConcurrentHashMap<>();
    }

    public void addServerMethod(String m, ServerFunctionInfo info) {
      serverMethods.put(m, info);
    }

    public void addClientMethod(String m, ClientInfo info) {
      clientMethods.put(m, info);
    }
  }

  private static final List<FunctionInfo> serviceInstances = new ArrayList<>();
  private static final Map<String, CompletableFuture<RPCResponseMessage>> pendingCalls = new ConcurrentHashMap<>();
  private static final HashSet<String> subscribedTopics = new HashSet<>();
  private static AutobahnClient client;

  public static void setAutobahnClient(AutobahnClient client) {
    AutobahnRPC.client = client;
  }

  /**
   * Creates a proxy implementation for an interface with @ClientFunction methods.
   * This allows users to define only method signatures and get automatic RPC
   * implementations.
   *
   * @param interfaceClass The interface class with @ClientFunction annotated
   *                       methods
   * @return A proxy implementation that makes RPC calls automatically
   */
  @SuppressWarnings("unchecked")
  public static <T> T createRPCClient(Class<T> interfaceClass) {
    if (!interfaceClass.isInterface()) {
      throw new IllegalArgumentException(
          "Only interfaces are supported for RPC client generation");
    }

    if (client == null) {
      throw new IllegalStateException(
          "AutobahnClient not set. Call setAutobahnClient() first.");
    }

    setupClientSubscriptions(interfaceClass);

    return (T) Proxy.newProxyInstance(
        interfaceClass.getClassLoader(),
        new Class<?>[] { interfaceClass },
        new RPCInvocationHandler(interfaceClass));
  }

  /**
   * Sets up subscriptions for response handling for all @ClientFunction methods
   * in an interface
   */
  private static void setupClientSubscriptions(Class<?> interfaceClass) {
    for (Method method : interfaceClass.getDeclaredMethods()) {
      if (method.isAnnotationPresent(ClientFunction.class)) {
        String topic = fromFunctionSignatureToPub(method);

        if (!subscribedTopics.contains(topic)) {
          client.subscribe(
              topic,
              NamedCallback.FromConsumer(message -> {
                try {
                  onMessageClient(message);
                } catch (InvalidProtocolBufferException e) {
                  System.err.println(
                      "Failed to parse response message: " + e.getMessage());
                  e.printStackTrace();
                }
              }));

          subscribedTopics.add(topic);
        }
      }
    }
  }

  /**
   * InvocationHandler that automatically implements @ClientFunction methods
   */
  private static class RPCInvocationHandler implements InvocationHandler {

    private final Class<?> interfaceClass;

    public RPCInvocationHandler(Class<?> interfaceClass) {
      this.interfaceClass = interfaceClass;
    }

    @Override
    public Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable {
      if (method.getDeclaringClass() == Object.class) {
        switch (method.getName()) {
          case "toString":
            return "RPCProxy[" + interfaceClass.getSimpleName() + "]";
          case "equals":
            return proxy == args[0];
          case "hashCode":
            return System.identityHashCode(proxy);
          default:
            throw new UnsupportedOperationException(
                "Method " + method.getName() + " not supported");
        }
      }

      // Check if method has @ClientFunction annotation
      ClientFunction annotation = method.getAnnotation(ClientFunction.class);
      if (annotation == null) {
        throw new UnsupportedOperationException(
            "Method " + method.getName() + " must have @ClientFunction annotation");
      }

      // Validate method signature
      try {
        checkMethodInputOutput(method);
      } catch (Exception e) {
        throw new RuntimeException(
            "Invalid RPC method signature: " + method.getName(),
            e);
      }

      // Extract parameters
      String methodName = method.getName();
      GeneratedMessageV3 request = null;
      if (args != null && args.length > 0) {
        request = (GeneratedMessageV3) args[0];
      }

      Class<?> returnType = method.getReturnType();
      long timeoutMs = annotation.timeoutMs();

      // Make the RPC call
      if (returnType == void.class || returnType == Void.class) {
        makeRPCCall(methodName, request, timeoutMs);
        return null;
      } else {
        return makeRPCCall(methodName, request, returnType, timeoutMs);
      }
    }
  }

  public static void registerRPCServices(Class<?>... classes) {
    for (Class<?> clazz : classes) {
      try {
        registerRPCService(clazz);
      } catch (Exception e) {
        throw new RuntimeException(
            "Failed to register RPC service: " + clazz.getName(),
            e);
      }
    }
  }

  public static void registerRPCService(Class<?> clazz) throws Exception {
    Object instance = clazz.getDeclaredConstructor().newInstance();
    FunctionInfo infoInstance = new FunctionInfo(instance);

    for (Method method : Stream
        .of(clazz.getDeclaredMethods())
        .filter(AutobahnRPC::isRPCMethod)
        .toList()) {
      checkMethodInputOutput(method);

      String pubOrSubString = fromFunctionSignatureToPub(method);

      if (method.isAnnotationPresent(ServerFunction.class)) {
        handleServerFunction(method, infoInstance, pubOrSubString);
        continue;
      }

      handleClientFunction(method, infoInstance, pubOrSubString);
    }

    serviceInstances.add(infoInstance);
  }

  private static void handleClientFunction(
      Method method,
      FunctionInfo infoInstance,
      String pubOrSubString) {
    ClientFunction annotation = method.getAnnotation(ClientFunction.class);

    long timeoutMs = annotation.timeoutMs();
    infoInstance.addClientMethod(
        pubOrSubString,
        new ClientInfo(timeoutMs, method));
  }

  private static void handleServerFunction(
      Method method,
      FunctionInfo infoInstance,
      String pubOrSubString) {
    infoInstance.addServerMethod(
        pubOrSubString,
        new ServerFunctionInfo(method));

    client.subscribe(
        pubOrSubString,
        NamedCallback.FromConsumer(message -> {
          try {
            onMessageServer(pubOrSubString, message);
          } catch (InvalidProtocolBufferException e) {
            throw new RuntimeException(
                "Failed to parse request message: " + e.getMessage(),
                e);
          }
        }));
  }

  private static boolean isRPCMethod(Method m) {
    return (m.isAnnotationPresent(ServerFunction.class) ||
        m.isAnnotationPresent(ClientFunction.class));
  }

  private static void onMessageServer(String topic, byte[] message)
      throws InvalidProtocolBufferException {
    final RPCRequestMessage requestMessage = RPCRequestMessage.parseFrom(
        message);

    FunctionInfo info = getFunctionInfo(topic);
    assert info != null;

    ServerFunctionInfo serverInfo = info.getServerMethods().get(topic);
    assert serverInfo != null;

    Method method = serverInfo.getMethod();

    Class<?> paramType = method.getParameterTypes()[0];
    final GeneratedMessageV3 inputMessage;
    if (!requestMessage.getPayload().isEmpty() && paramType != void.class) {
      try {
        Method parseFrom = paramType.getMethod("parseFrom", byte[].class);
        inputMessage = (GeneratedMessageV3) parseFrom.invoke(
            null,
            requestMessage.getPayload());
      } catch (
          NoSuchMethodException
          | SecurityException
          | IllegalAccessException
          | InvocationTargetException e) {
        throw new RuntimeException(
            "Failed to parse input message: " + e.getMessage(),
            e);
      }
    } else {
      inputMessage = null;
    }

    new Thread(() -> {
      RPCResponseMessage.Builder responseMessage = RPCResponseMessage
          .newBuilder()
          .setMessageType(RPCMessageType.RPC_RESPONSE)
          .setResponseType(RPCResponseType.RPC_RESPONSE_SUCCESS)
          .setCallId(requestMessage.getCallId())
          .setPayload(ByteString.EMPTY);

      try {
        Object result = method.invoke(info.getServiceClass(), inputMessage);

        if (result instanceof GeneratedMessageV3) {
          responseMessage.setPayload(
              ((GeneratedMessageV3) result).toByteString());
        } else if (method.getReturnType() != void.class) {
          responseMessage.setResponseType(RPCResponseType.UNRECOGNIZED);
          responseMessage.setPayload(
              ByteString.copyFromUtf8(
                  "ERROR WITH RETURN TYPE: " + method.getReturnType().getName()));
        }
      } catch (
          IllegalAccessException
          | IllegalArgumentException
          | InvocationTargetException e) {
        responseMessage.setResponseType(RPCResponseType.RPC_RESPONSE_ERROR);
        responseMessage.setPayload(ByteString.copyFromUtf8(e.getMessage()));
        e.printStackTrace();
      }

      client.publish(topic, responseMessage.build().toByteArray()).join();
    })
        .start();
  }

  private static void onMessageClient(byte[] message)
      throws InvalidProtocolBufferException {
    final RPCResponseMessage responseMessage = RPCResponseMessage.parseFrom(
        message);

    String callId = responseMessage.getCallId();
    CompletableFuture<RPCResponseMessage> pendingCall = pendingCalls.get(
        callId);

    if (pendingCall != null) {
      pendingCall.complete(responseMessage);
    } else {
      System.err.println("Received response for unknown call ID: " + callId);
    }
  }

  private static FunctionInfo getFunctionInfo(String topic) {
    return serviceInstances
        .stream()
        .filter(info -> info.getServerMethods().containsKey(topic))
        .findFirst()
        .orElse(null);
  }

  private static void checkMethodInputOutput(Method method) throws Exception {
    Exception eToThrow = new Exception(
        "The method " +
            method.getName() +
            " is not a valid RPC method since it must have no parameters or one parameter that is a protobuf message");

    // For interface methods, we don't require static/public modifiers
    if (!method.getDeclaringClass().isInterface()) {
      int modifiers = method.getModifiers();
      if (!Modifier.isPublic(modifiers) || !Modifier.isStatic(modifiers)) {
        throw eToThrow;
      }
    }

    Class<?>[] paramTypes = method.getParameterTypes();
    Class<?> returnType = method.getReturnType();

    if (paramTypes.length != 0 && paramTypes.length != 1) {
      throw eToThrow;
    }

    if (paramTypes.length == 1 &&
        !GeneratedMessageV3.class.isAssignableFrom(paramTypes[0])) {
      throw eToThrow;
    }

    if (returnType != void.class &&
        !GeneratedMessageV3.class.isAssignableFrom(returnType)) {
      throw eToThrow;
    }
  }

  private static String fromFunctionSignatureToPub(Method method) {
    StringBuilder sig = new StringBuilder(method.getName());

    for (Class<?> paramType : method.getParameterTypes()) {
      sig
          .append("_")
          .append(fromJavaDefaultTypeToPython(paramType.getTypeName()));
    }

    Class<?> ret = method.getReturnType();
    String pyRet = fromJavaDefaultTypeToPython(ret.getTypeName());

    sig.append("_").append(pyRet);
    return sig.toString();
  }

  private static String fromJavaDefaultTypeToPython(String type) {
    switch (type) {
      case "void":
        return "None";
      case "int":
      case "long":
        return "int";
      case "double":
      case "float":
        return "float";
      case "boolean":
        return "bool";
      case "String":
        return "str";
      case "List":
        return "list";
      case "Map":
        return "dict";
      default:
        return type;
    }
  }

  /**
   * Makes an RPC call to a remote method.
   * Internal method used by the proxy implementations.
   */
  private static void makeRPCCall(
      String methodName,
      GeneratedMessageV3 request,
      long timeoutMs) throws Exception {
    makeRPCCall(methodName, request, void.class, timeoutMs);
  }

  /**
   * Makes an RPC call to a remote method with a return value.
   * Internal method used by the proxy implementations.
   */
  @SuppressWarnings("unchecked")
  private static <T> T makeRPCCall(
      String methodName,
      GeneratedMessageV3 request,
      Class<T> responseType,
      long timeoutMs) throws Exception {
    if (client == null) {
      throw new IllegalStateException(
          "AutobahnClient not set. Call setAutobahnClient() first.");
    }

    // Generate unique call ID
    String callId = UUID.randomUUID().toString();

    // Build the RPC request message
    RPCRequestMessage.Builder requestBuilder = RPCRequestMessage
        .newBuilder()
        .setMessageType(RPCMessageType.RPC_REQUEST)
        .setCallId(callId);

    if (request != null) {
      requestBuilder.setPayload(request.toByteString());
    } else {
      requestBuilder.setPayload(ByteString.EMPTY);
    }

    RPCRequestMessage requestMessage = requestBuilder.build();

    // Create future for response
    CompletableFuture<RPCResponseMessage> responseFuture = new CompletableFuture<>();
    pendingCalls.put(callId, responseFuture);

    // Generate the topic name (same logic as server side)
    String topic = generateTopicName(
        methodName,
        request != null ? request.getClass() : null,
        responseType);

    try {
      // Publish the request
      client.publish(topic, requestMessage.toByteArray()).join();

      // Wait for response with timeout
      RPCResponseMessage response = responseFuture.get(
          timeoutMs,
          TimeUnit.MILLISECONDS);

      // Check if the response indicates success
      if (response.getResponseType() != RPCResponseType.RPC_RESPONSE_SUCCESS) {
        String errorMessage = response.getPayload().toStringUtf8();
        throw new RuntimeException("RPC call failed: " + errorMessage);
      }

      // Parse and return the response
      if (response.getPayload().isEmpty() || responseType == void.class) {
        return null;
      }

      Method parseFrom = responseType.getMethod("parseFrom", byte[].class);
      return (T) parseFrom.invoke(null, response.getPayload().toByteArray());
    } catch (TimeoutException e) {
      throw new RuntimeException(
          "RPC call timed out after " + timeoutMs + "ms",
          e);
    } finally {
      // Clean up pending call
      pendingCalls.remove(callId);
    }
  }

  /**
   * Generates a topic name based on method signature.
   * This should match the logic used by the server side.
   */
  private static String generateTopicName(
      String methodName,
      Class<?> paramType,
      Class<?> returnType) {
    StringBuilder sig = new StringBuilder(methodName);

    if (paramType != null) {
      sig
          .append("_")
          .append(fromJavaDefaultTypeToPython(paramType.getTypeName()));
    }

    String pyRet = fromJavaDefaultTypeToPython(returnType.getTypeName());
    sig.append("_").append(pyRet);

    return sig.toString();
  }
}
