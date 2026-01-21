package autobahn.client.rpc.client;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.concurrent.CompletableFuture;

/**
 * Annotation to mark methods as RPC callable (client-side RPC calls).
 * Similar to @rpc_callable in the Python implementation.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface ClientFunction {
  long timeoutMs() default 3000;
}
