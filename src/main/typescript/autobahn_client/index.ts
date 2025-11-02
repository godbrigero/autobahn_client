// src/lib/AutobahnClient.ts - Purpose: minimal pub/sub websocket client using protobuf frames
import {
  MessageType,
  PublishMessage,
  TopicMessage,
  UnsubscribeMessage,
} from "./proto/message";

type PayloadCallback = (payload: Uint8Array) => Promise<void>;

export class Address {
  private url: string;

  constructor(host: string, port: number) {
    this.url = `ws://${host}:${port}`;
  }

  makeUrl() {
    return this.url;
  }
}

export class AutobahnClient {
  private address: Address;
  private ws: WebSocket | null = null;
  private reconnect: boolean;
  private reconnectInterval: number;
  private callbacks = new Map<string, PayloadCallback>();
  private firstSub = true;
  private connected = false;

  constructor(
    address: Address,
    reconnect = true,
    reconnectIntervalSeconds = 1.0
  ) {
    this.address = address;
    this.reconnect = reconnect;
    this.reconnectInterval = reconnectIntervalSeconds * 1000;
  }

  /** Start the connection */
  public begin() {
    if (this.connected) {
      return;
    }

    this.connect();
  }

  /** Check if the client is connected */
  public isConnected(): boolean {
    return this.connected;
  }

  private connect() {
    const url = this.address.makeUrl();
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.connected = true;
      for (const topic of this.callbacks.keys()) {
        const msg = TopicMessage.create({
          messageType: MessageType.SUBSCRIBE,
          topic,
        });
        this.ws!.send(TopicMessage.encode(msg).finish());
      }
      this.firstSub = false;
    };

    this.ws.onmessage = (evt) => this.handleMessage(evt);
    this.ws.onclose = () => {
      this.connected = false;
      this.ws = null;
      if (this.reconnect)
        setTimeout(() => this.connect(), this.reconnectInterval);
    };
    this.ws.onerror = (err) => {
      console.error("WebSocket error", err);
      this.ws?.close();
    };
  }

  private async handleMessage(evt: MessageEvent) {
    if (typeof evt.data === "string") return;
    const bytes = new Uint8Array(evt.data as ArrayBuffer);
    let msg: PublishMessage;
    try {
      msg = PublishMessage.decode(bytes);
    } catch (e) {
      console.error("Failed to decode PublishMessage", e);
      return;
    }
    if (msg.messageType === MessageType.PUBLISH) {
      const cb = this.callbacks.get(msg.topic);
      if (cb) await cb(msg.payload);
    }
  }

  /** Subscribe to a topic; callback receives raw bytes */
  public subscribe(topic: string, callback: PayloadCallback) {
    this.callbacks.set(topic, callback);

    if (this.ws?.readyState === WebSocket.OPEN) {
      const msg = TopicMessage.create({
        messageType: MessageType.SUBSCRIBE,
        topic,
      });
      this.ws.send(TopicMessage.encode(msg).finish());
    }
  }

  /** Unsubscribe from a topic */
  public unsubscribe(topic: string) {
    this.callbacks.delete(topic);

    if (this.ws?.readyState === WebSocket.OPEN) {
      const msg = UnsubscribeMessage.create({
        messageType: MessageType.UNSUBSCRIBE,
        topic,
      });
      this.ws.send(UnsubscribeMessage.encode(msg).finish());
    }
  }

  /** Publish a payload to a topic */
  public publish(topic: string, payload: Uint8Array) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      if (!this.reconnect) {
        throw new Error("WebSocket not connected. Call begin() first.");
      }
      return;
    }

    const msg = PublishMessage.create({
      messageType: MessageType.PUBLISH,
      topic,
      payload,
    });

    this.ws.send(PublishMessage.encode(msg).finish());
  }
}
