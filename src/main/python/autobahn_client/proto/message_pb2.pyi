from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SERVER_STATE: _ClassVar[MessageType]
    SERVER_FORWARD: _ClassVar[MessageType]
    PUBLISH: _ClassVar[MessageType]
    SUBSCRIBE: _ClassVar[MessageType]
    UNSUBSCRIBE: _ClassVar[MessageType]

class RPCMessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RPC_REQUEST: _ClassVar[RPCMessageType]
    RPC_RESPONSE: _ClassVar[RPCMessageType]

class RPCResponseType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RPC_RESPONSE_SUCCESS: _ClassVar[RPCResponseType]
    RPC_RESPONSE_ERROR: _ClassVar[RPCResponseType]
SERVER_STATE: MessageType
SERVER_FORWARD: MessageType
PUBLISH: MessageType
SUBSCRIBE: MessageType
UNSUBSCRIBE: MessageType
RPC_REQUEST: RPCMessageType
RPC_RESPONSE: RPCMessageType
RPC_RESPONSE_SUCCESS: RPCResponseType
RPC_RESPONSE_ERROR: RPCResponseType

class AbstractMessage(_message.Message):
    __slots__ = ("message_type",)
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ...) -> None: ...

class ServerStateMessage(_message.Message):
    __slots__ = ("message_type", "uuid", "topics")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    UUID_FIELD_NUMBER: _ClassVar[int]
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    uuid: str
    topics: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ..., uuid: _Optional[str] = ..., topics: _Optional[_Iterable[str]] = ...) -> None: ...

class ServerForwardMessage(_message.Message):
    __slots__ = ("message_type", "payload")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    payload: bytes
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ..., payload: _Optional[bytes] = ...) -> None: ...

class TopicMessage(_message.Message):
    __slots__ = ("message_type", "topic")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    topic: str
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ..., topic: _Optional[str] = ...) -> None: ...

class PublishMessage(_message.Message):
    __slots__ = ("message_type", "topic", "payload")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    topic: str
    payload: bytes
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ..., topic: _Optional[str] = ..., payload: _Optional[bytes] = ...) -> None: ...

class UnsubscribeMessage(_message.Message):
    __slots__ = ("message_type", "topic")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    message_type: MessageType
    topic: str
    def __init__(self, message_type: _Optional[_Union[MessageType, str]] = ..., topic: _Optional[str] = ...) -> None: ...

class RPCMessage(_message.Message):
    __slots__ = ("message_type", "call_id")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    message_type: RPCMessageType
    call_id: str
    def __init__(self, message_type: _Optional[_Union[RPCMessageType, str]] = ..., call_id: _Optional[str] = ...) -> None: ...

class RPCRequestMessage(_message.Message):
    __slots__ = ("message_type", "call_id", "payload")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    message_type: RPCMessageType
    call_id: str
    payload: bytes
    def __init__(self, message_type: _Optional[_Union[RPCMessageType, str]] = ..., call_id: _Optional[str] = ..., payload: _Optional[bytes] = ...) -> None: ...

class RPCResponseMessage(_message.Message):
    __slots__ = ("message_type", "call_id", "response_type", "payload")
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    message_type: RPCMessageType
    call_id: str
    response_type: RPCResponseType
    payload: bytes
    def __init__(self, message_type: _Optional[_Union[RPCMessageType, str]] = ..., call_id: _Optional[str] = ..., response_type: _Optional[_Union[RPCResponseType, str]] = ..., payload: _Optional[bytes] = ...) -> None: ...

class RPCEmpty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
