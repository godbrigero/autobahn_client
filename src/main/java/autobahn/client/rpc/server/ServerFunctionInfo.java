package autobahn.client.rpc.server;

import java.lang.reflect.Method;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Information about a registered RPC function.
 * Similar to RPCFunctionInfo in the Python implementation.
 */
@Getter
@AllArgsConstructor
public class ServerFunctionInfo {

  private Method method;
}
