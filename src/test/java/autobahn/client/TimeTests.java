package autobahn.client;

import java.util.Arrays;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

public class TimeTests {
    private static final String topic = "test";
    private static final int numberOfMessages = 1000;
    private static final boolean shouldConnect = false;

    private static byte[] generateRandomBytes(int size) {
        byte[] bytes = new byte[size];
        new Random().nextBytes(bytes);
        return bytes;
    }

    private static byte[] encodeTime(byte[] bytes) {
        long currentTimeMillis = System.nanoTime();
        byte[] timeBytes = new byte[8];
        for (int i = 7; i >= 0; i--) {
            timeBytes[i] = (byte) (currentTimeMillis & 0xFF);
            currentTimeMillis >>= 8;
        }
        byte[] result = new byte[bytes.length + 8];
        System.arraycopy(bytes, 0, result, 0, bytes.length);
        System.arraycopy(timeBytes, 0, result, bytes.length, 8);
        return result;
    }

    private static Object[] decodeTime(byte[] bytes) {
        if (bytes.length < 8) {
            throw new IllegalArgumentException("Input byte array too short to contain timestamp.");
        }
        byte[] payload = Arrays.copyOfRange(bytes, 0, bytes.length - 8);
        byte[] timeBytes = Arrays.copyOfRange(bytes, bytes.length - 8, bytes.length);
        long timestamp = 0;
        for (int i = 0; i < 8; i++) {
            timestamp = (timestamp << 8) | (timeBytes[i] & 0xFF);
        }
        return new Object[] { payload, timestamp };
    }

    private static double printStatistics(long[] times) {
        System.out.println("Average time: " + Arrays.stream(times).average().getAsDouble() / 1000000);
        System.out.println("Median time: " + Arrays.stream(times).sorted().toArray()[times.length / 2] / 1000000);
        System.out.println("Min time: " + Arrays.stream(times).min().getAsLong() / 1000000);
        System.out.println("Max time: " + Arrays.stream(times).max().getAsLong() / 1000000);
        double average = Arrays.stream(times).average().getAsDouble() / 1000000;
        double variance = Arrays.stream(times)
                .mapToDouble(t -> t - average)
                .map(diff -> diff * diff)
                .average()
                .orElse(0.0);
        double stdDeviation = Math.sqrt(variance);
        System.out.println("Standard deviation: " + stdDeviation / 1000000);

        return average;
    }

    private static long[] sendNMessages(AutobahnClient client, int numberOfMessages, byte[] bytes, String topic) {
        final long[] times = new long[numberOfMessages];
        final AtomicInteger receivedMessages = new AtomicInteger(0);

        client.subscribe(topic, NamedCallback.FromConsumer((byte[] data) -> {
            Object[] decoded = decodeTime(data);
            times[receivedMessages.get()] = System.nanoTime() - (long) decoded[1];
            receivedMessages.incrementAndGet();
        })).join();

        for (int i = 0; i < numberOfMessages; i++) {
            client.publish(topic, encodeTime(bytes)).join();
        }

        while (receivedMessages.get() != numberOfMessages) {
            try {
                Thread.sleep(10);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        }

        return times;
    }

    @Test
    public void testTime0Mb() {
        if (!shouldConnect)
            return;

        byte[] bytes = generateRandomBytes(1);
        AutobahnClient client = new AutobahnClient(new Address("localhost", 8080));
        client.begin().join();

        long[] times = sendNMessages(client, numberOfMessages, bytes, topic);

        double average = printStatistics(times);
        System.out.println("Average: " + average);
        assert average > 0;
    }

    @Test
    public void testTime1Mb() {
        if (!shouldConnect)
            return;

        byte[] bytes = generateRandomBytes(1024 * 1024);
        AutobahnClient client = new AutobahnClient(new Address("localhost", 8080));
        client.begin().join();

        long[] times = sendNMessages(client, numberOfMessages, bytes, topic);

        double average = printStatistics(times);
        System.out.println("Average: " + average);
        assert average > 0;
    }

    @Test
    public void testTime4Mb() {
        if (!shouldConnect)
            return;

        byte[] bytes = generateRandomBytes(1024 * 1024 * 4);
        AutobahnClient client = new AutobahnClient(new Address("localhost", 8080));
        client.begin().join();

        long[] times = sendNMessages(client, numberOfMessages, bytes, topic);

        double average = printStatistics(times);
        System.out.println("Average: " + average);
        assert average > 0;
    }
}
