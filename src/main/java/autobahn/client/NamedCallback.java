package autobahn.client;

import java.util.UUID;
import java.util.function.Consumer;

public abstract class NamedCallback implements Consumer<byte[]> {

  protected String code = UUID.randomUUID().toString();

  public String getCode() {
    return code;
  }

  public static NamedCallback FromConsumer(Consumer<byte[]> consumer) {
    return new NamedCallback() {
      @Override
      public void accept(byte[] message) {
        consumer.accept(message);
      }
    };
  }

  @Override
  public boolean equals(Object obj) {
    if (obj instanceof NamedCallback) {
      return ((NamedCallback) obj).getCode().equals(code);
    }
    return false;
  }
}
