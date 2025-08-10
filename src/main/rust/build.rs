use std::env;
use std::path::PathBuf;
use walkdir::WalkDir;

extern crate prost_build;

fn main() {
    let manifest_dir = env::var("CARGO_MANIFEST_DIR").unwrap();

    // Generate protobuf bindings. For publishability, keep protos within the crate package.
    let proto_dir = PathBuf::from(&manifest_dir).join("proto");
    let proto_files: Vec<String> = WalkDir::new(&proto_dir)
        .follow_links(true)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "proto"))
        .map(|e| e.path().to_str().unwrap().to_string())
        .collect();

    let include_dirs: Vec<String> = WalkDir::new(&proto_dir)
        .follow_links(true)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .map(|e| e.path().to_str().unwrap().to_string())
        .collect();

    prost_build::compile_protos(&proto_files, &include_dirs).unwrap();
}
