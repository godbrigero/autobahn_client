protoc:
	protoc --proto_path=proto --python_out=./autobahn_client/proto/ --pyi_out=./autobahn_client/proto/ message.proto

grpc:
	python -m grpc_tools.protoc --proto_path=proto --python_out=./autobahn_client/proto/ --grpc_python_out=./autobahn_client/proto/ --pyi_out=./autobahn_client/proto/ message.proto

# Generate with mypy-protobuf for better type stubs
protoc-mypy:
	protoc --proto_path=proto --python_out=./autobahn_client/proto/ --mypy_out=./autobahn_client/proto/ message.proto

grpc-mypy:
	python -m grpc_tools.protoc --proto_path=proto --python_out=./autobahn_client/proto/ --grpc_python_out=./autobahn_client/proto/ --mypy_out=./autobahn_client/proto/ message.proto

# Generate everything with basic type stubs
all:
	protoc --proto_path=proto --python_out=./autobahn_client/proto/ --pyi_out=./autobahn_client/proto/ message.proto
	python -m grpc_tools.protoc --proto_path=proto --python_out=./autobahn_client/proto/ --grpc_python_out=./autobahn_client/proto/ --pyi_out=./autobahn_client/proto/ message.proto

# Generate everything with mypy-protobuf (better type stubs)
all-mypy:
	python -m grpc_tools.protoc --proto_path=proto --python_out=./autobahn_client/proto/ --grpc_python_out=./autobahn_client/proto/ --mypy_out=./autobahn_client/proto/ message.proto

# Clean generated files
clean:
	rm -f autobahn_client/proto/message_pb2.py
	rm -f autobahn_client/proto/message_pb2.pyi  
	rm -f autobahn_client/proto/message_pb2_grpc.py

.PHONY: protoc grpc protoc-mypy grpc-mypy all all-mypy clean

