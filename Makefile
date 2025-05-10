protoc:
	protoc --proto_path=proto --python_out=./autobahn_client/proto/ --pyi_out=./autobahn_client/proto message.proto

