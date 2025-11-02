import { Address, AutobahnClient } from "autobahn-client";

function main() {
  const client = new AutobahnClient(new Address("localhost", 8080));
  client.begin();

  client.subscribe("test", async (payload) => {
    console.log(payload);
  });

  client.publish("test", new Uint8Array([1, 2, 3]));
}

main();
