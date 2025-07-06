pub mod autobahn;

pub mod proto {
    pub mod autobahn {
        include!(concat!(env!("OUT_DIR"), "/proto.autobahn.rs"));
    }
}
