package autobahn.client;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class Address {

  private final String host;
  private final int port;

  public static Address fromString(String address) {
    String[] parts = address.split(":");
    return new Address(parts[0], Integer.parseInt(parts[1]));
  }

  public static Address fromHostAndPort(String host, String port) {
    return new Address(host, Integer.parseInt(port));
  }

  public String makeUrl() {
    return "ws://" + host + ":" + port;
  }

  public String toString() {
    return makeUrl();
  }
}
