PYTHONPATH=.venv/bin/python

protoc:
	protoc --proto_path=proto --python_out=./src/main/python/autobahn_client/proto/ --pyi_out=./src/main/python/autobahn_client/proto/ message.proto

clean:
	rm -f src/main/python/autobahn_client/proto/message_pb2.py
	rm -f src/main/python/autobahn_client/proto/message_pb2.pyi  
	rm -f src/main/python/autobahn_client/proto/message_pb2_grpc.py

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