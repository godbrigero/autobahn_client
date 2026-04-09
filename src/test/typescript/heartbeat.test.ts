import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Address, AutobahnClient } from "../../main/typescript/autobahn_client/index";
import {
  AbstractMessage,
  HeartbeatMessage,
  MessageType,
} from "../../main/typescript/autobahn_client/proto/message";

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  binaryType = "blob";
  sent: Uint8Array[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: ArrayBufferLike | ArrayBufferView): void {
    if (ArrayBuffer.isView(data)) {
      const slice = data.buffer.slice(
        data.byteOffset,
        data.byteOffset + data.byteLength
      );
      this.sent.push(new Uint8Array(slice));
      return;
    }

    this.sent.push(new Uint8Array(data));
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({} as CloseEvent);
  }

  emitOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({} as Event);
  }

  emitMessage(data: Uint8Array): void {
    const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    this.onmessage?.({ data: buffer } as MessageEvent);
  }
}

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const findHeartbeat = (frames: Uint8Array[]) => {
  const heartbeatFrame = frames.find((frame) => {
    const msg = AbstractMessage.decode(frame);
    return msg.messageType === MessageType.HEARTBEAT;
  });

  expect(heartbeatFrame).toBeDefined();
  return HeartbeatMessage.decode(heartbeatFrame!);
};

describe("AutobahnClient heartbeat", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("replies to heartbeats with all subscribed topics", async () => {
    const client = new AutobahnClient(new Address("localhost", 8080), false);
    client.subscribe("alpha", async () => {});
    client.subscribe("beta", async () => {});

    client.begin();
    const ws = MockWebSocket.instances[0];
    ws.emitOpen();
    ws.sent = [];

    ws.emitMessage(
      HeartbeatMessage.encode({
        messageType: MessageType.HEARTBEAT,
        uuid: "server",
        topics: [],
      }).finish()
    );
    await flush();

    const heartbeat = findHeartbeat(ws.sent);
    expect([...heartbeat.topics].sort()).toEqual(["alpha", "beta"]);
  });

  it("omits unsubscribed topics from heartbeat replies", async () => {
    const client = new AutobahnClient(new Address("localhost", 8080), false);
    client.subscribe("alpha", async () => {});
    client.subscribe("beta", async () => {});

    client.begin();
    const ws = MockWebSocket.instances[0];
    ws.emitOpen();

    client.unsubscribe("beta");
    ws.sent = [];

    ws.emitMessage(
      HeartbeatMessage.encode({
        messageType: MessageType.HEARTBEAT,
        uuid: "server",
        topics: [],
      }).finish()
    );
    await flush();

    const heartbeat = findHeartbeat(ws.sent);
    expect(heartbeat.topics).toEqual(["alpha"]);
  });
});
