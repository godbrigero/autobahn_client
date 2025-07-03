protoc:
	protoc --proto_path=proto --python_out=./src/main/python/autobahn_client/proto/ --pyi_out=./src/main/python/autobahn_client/proto/ message.proto

clean:
	rm -f src/main/python/autobahn_client/proto/message_pb2.py
	rm -f src/main/python/autobahn_client/proto/message_pb2.pyi  
	rm -f src/main/python/autobahn_client/proto/message_pb2_grpc.py

.PHONY: protoc clean

