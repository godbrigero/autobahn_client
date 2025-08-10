package autobahn.client.rpc.client;

import com.google.protobuf.GeneratedMessageV3;
import java.lang.reflect.Method;
import java.util.function.Function;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Configuration for an RPC callable method.
 * Stores information needed to make RPC calls.
 */
@Getter
@AllArgsConstructor
public class ClientInfo {

  private long timeoutMs;
  private Method toCall;
}
