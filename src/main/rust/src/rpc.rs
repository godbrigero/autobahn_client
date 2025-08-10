use std::fmt::Display;

pub mod client;
pub mod server;

#[derive(Debug)]
pub enum RPCError {
    ConnectionError(String),
    SerializationError(String),
    DeserializationError(String),
    TimeoutError(String),
    ErrorResponse(String),
    Other(String),
}

impl Display for RPCError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Avoid recursion: do not call to_string() inside Display
        match self {
            RPCError::ConnectionError(msg) => write!(f, "ConnectionError: {}", msg),
            RPCError::SerializationError(msg) => write!(f, "SerializationError: {}", msg),
            RPCError::DeserializationError(msg) => write!(f, "DeserializationError: {}", msg),
            RPCError::TimeoutError(msg) => write!(f, "TimeoutError: {}", msg),
            RPCError::ErrorResponse(msg) => write!(f, "ErrorResponse: {}", msg),
            RPCError::Other(msg) => write!(f, "Other: {}", msg),
        }
    }
}

impl RPCError {
    pub fn default() -> Self {
        Self::Other("".to_string())
    }
}

impl std::error::Error for RPCError {}
