PYTHONPATH=.venv/bin/python

protoc:
	@echo "Compiling protobuf files for Python and TypeScript..."
	@which protoc > /dev/null || (echo "Error: protoc is not installed or not in PATH."; exit 1)
	@which npm > /dev/null || (echo "Error: npm is not installed. Please install Node.js and npm."; exit 1)
	@test -d node_modules/ts-proto || (echo "Installing TypeScript dependencies..."; npm install)
	@mkdir -p ./src/main/typescript/autobahn_client/proto/
	protoc --proto_path=proto \
		--python_out=./src/main/python/autobahn_client/proto/ \
		--pyi_out=./src/main/python/autobahn_client/proto/ \
		--plugin=./node_modules/.bin/protoc-gen-ts_proto \
		--ts_proto_out=./src/main/typescript/autobahn_client/proto/ \
		message.proto

clean:
	rm -f src/main/python/autobahn_client/proto/message_pb2.py
	rm -f src/main/python/autobahn_client/proto/message_pb2.pyi  
	rm -f src/main/python/autobahn_client/proto/message_pb2_grpc.py
	rm -rf src/main/typescript/autobahn_client/proto/*.ts

.PHONY: protoc clean

test_4mb:
	$(PYTHONPATH) -m src.test.python.test_time --test 4mb

test_8mb:
	$(PYTHONPATH) -m src.test.python.test_time --test 8mb

test_0mb:
	$(PYTHONPATH) -m src.test.python.test_time --test 0mb

test_noms:
	$(PYTHONPATH) -m src.test.python.test_time --test noms

test_noms_4mb:
	$(PYTHONPATH) -m src.test.python.test_time --test noms_4mb

test_multi_message_0mb:
	$(PYTHONPATH) -m src.test.python.test_time --test multi_message_0mb

test_multi_subscribe:
	$(PYTHONPATH) -m src.test.python.test_time --test multi_subscribe