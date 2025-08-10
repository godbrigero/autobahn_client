use bytes::{Bytes, BytesMut};
use prost::Message;

pub fn build_proto_message<T: Message>(message: &T) -> Vec<u8> {
    return {
        let mut buf = BytesMut::new();
        let _ = message.encode(&mut buf);
        buf.to_vec()
    };
}

pub fn deserialize_partial<T: Default + Message>(buf: &[u8]) -> Result<T, prost::DecodeError> {
    let mut instance = T::default();
    instance.merge(buf)?;
    Ok(instance)
}
