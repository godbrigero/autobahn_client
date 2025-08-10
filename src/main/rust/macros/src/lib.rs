use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{parse_macro_input, FnArg, ItemFn, Pat, ReturnType, Type};

fn get_crate_token() -> proc_macro2::TokenStream {
    match std::env::var("CARGO_PKG_NAME") {
        Ok(ref name) if name == "autobahn-client" || name == "autobahn_client" => {
            quote::quote!(crate)
        }
        _ => quote::quote!(autobahn_client),
    }
}

/// Attribute macro to register a function as an RPC server handler.
/// This macro generates a function that can handle RPC requests with proper type safety
/// and registers it with the server function registry.
#[proc_macro_attribute]
pub fn server_function(_args: TokenStream, input: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(input as ItemFn);
    let fn_name = &input_fn.sig.ident;
    let _vis = &input_fn.vis;
    let inputs = &input_fn.sig.inputs;
    let output = &input_fn.sig.output;

    // Extract argument types for register_server_function
    let mut arg_types: Vec<syn::Type> = Vec::new();
    for arg in inputs.iter() {
        match arg {
            FnArg::Typed(pat_type) => {
                if is_primitive_type(&pat_type.ty) {
                    panic!("Primitive types are not allowed as RPC parameters. Type '{}' is a primitive type. Only protobuf message types are supported.",
                        quote::quote!(#pat_type.ty));
                }
                arg_types.push((*pat_type.ty).clone());
            }
            FnArg::Receiver(_) => panic!("Methods with `self` are not supported"),
        }
    }

    // Use crate root resolution
    let crate_token = get_crate_token();

    // Determine input and output types
    let input_type = if arg_types.is_empty() {
        quote! { #crate_token::proto::autobahn::RpcEmpty }
    } else {
        let ty = &arg_types[0];
        quote! { #ty }
    };
    let output_type = match output {
        ReturnType::Default => quote! { #crate_token::proto::autobahn::RpcEmpty },
        ReturnType::Type(_, ty) => quote! { #ty },
    };

    // Generate RPC name using the same logic as client_function
    let rpc_name = from_function_to_rpc_name(&input_fn);
    let topic = format!("RPC/FUNCTIONAL_SERVICE/{}", rpc_name);

    let register_fn_name = format_ident!("__register_{}", fn_name);

    // Create wrapper function that handles the Result<T, Box<dyn Error + Send + Sync>> conversion
    let wrapper_fn_name = format_ident!("{}_wrapper", fn_name);

    // Build the wrapper function parameters and call
    let (wrapper_params, fn_call) = if arg_types.is_empty() {
        (quote! { _input: #input_type }, quote! { #fn_name().await })
    } else {
        (
            quote! { input: #input_type },
            quote! { #fn_name(input).await },
        )
    };

    // Handle return type conversion
    let return_handling = match output {
        ReturnType::Default => {
            quote! {
                #fn_call;
                Ok(#crate_token::proto::autobahn::RpcEmpty::default())
            }
        }
        ReturnType::Type(_, _) => {
            quote! {
                Ok(#fn_call)
            }
        }
    };

    let gen = quote! {
        // Keep the original function
        #input_fn

        // Create a wrapper function that matches the expected signature
        async fn #wrapper_fn_name(
            #wrapper_params
        ) -> ::std::result::Result<#output_type, Box<dyn ::std::error::Error + Send + Sync>> {
            #return_handling
        }

        #[ctor::ctor]
        fn #register_fn_name() {
            #crate_token::rpc::server::register_server_function::<#input_type, #output_type, _, _>(
                #topic.to_string(),
                #wrapper_fn_name,
            );
        }
    };

    gen.into()
}

#[proc_macro_attribute]
pub fn client_function(_args: TokenStream, input: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(input as ItemFn);

    let original_fn_name = &input_fn.sig.ident;
    let vis = &input_fn.vis;
    let inputs = &input_fn.sig.inputs;
    let output = &input_fn.sig.output;

    // Collect argument identifiers and types
    let mut arg_idents: Vec<syn::Ident> = Vec::new();
    let mut arg_types: Vec<syn::Type> = Vec::new();

    for arg in inputs.iter() {
        match arg {
            FnArg::Typed(pat_type) => match &*pat_type.pat {
                Pat::Ident(pat_ident) => {
                    // Validate that the type is not a primitive
                    if is_primitive_type(&pat_type.ty) {
                        panic!("Primitive types are not allowed as RPC parameters. Type '{}' is a primitive type. Only protobuf message types are supported.", 
                               quote::quote!(#pat_type.ty));
                    }

                    arg_idents.push(pat_ident.ident.clone());
                    arg_types.push((*pat_type.ty).clone());
                }
                _ => panic!("Parameters must be simple identifiers (e.g., `x: T`)"),
            },
            FnArg::Receiver(_) => panic!("Methods with `self` are not supported"),
        }
    }

    // Use crate root resolution
    let crate_token = get_crate_token();

    let output_type = match output {
        ReturnType::Default => quote! { #crate_token::proto::autobahn::RpcEmpty },
        ReturnType::Type(_, ty) => quote! { #ty },
    };

    // Create an implementation function name to hold the original body
    let impl_fn_name = format_ident!("{}_impl", original_fn_name);
    let mut impl_fn = input_fn.clone();
    let mut impl_sig = impl_fn.sig.clone();
    impl_sig.ident = impl_fn_name.clone();
    impl_fn.sig = impl_sig;

    // Build wrapper parameter list
    let wrapper_params = if inputs.is_empty() {
        quote! { client: &::std::sync::Arc<#crate_token::autobahn::Autobahn>, timeout_ms: u64 }
    } else {
        quote! { client: &::std::sync::Arc<#crate_token::autobahn::Autobahn>, timeout_ms: u64, #inputs }
    };

    // Generate the RPC name string at compile time (match python: function name + arg types + return type)
    let rpc_name = from_function_to_rpc_name(&input_fn);

    // Build the argument handling with proper type bounds
    let (args_handling, input_type) = if arg_idents.is_empty() {
        (
            quote! { #crate_token::proto::autobahn::RpcEmpty::default() },
            quote! { #crate_token::proto::autobahn::RpcEmpty },
        )
    } else if arg_idents.len() == 1 {
        let first_arg = &arg_idents[0];
        let first_type = &arg_types[0];
        (quote! { #first_arg }, quote! { #first_type })
    } else {
        // TODO: Implement proper multi-argument support
        panic!("Multiple arguments not yet supported")
    };

    // Add trait bound assertions for the return type
    let output_assert = quote! {
        // Ensure the return type implements prost::Message + Default
        const _: fn() = || {
            fn assert_prost_message<T: ::prost::Message + ::std::default::Default>() {}
            let _ = assert_prost_message::<#output_type>;
        };
    };

    // Ensure each argument type implements prost::Message + Default (this excludes primitives)
    let input_assert = if arg_types.is_empty() {
        quote! {} // No assertions needed for functions with no parameters
    } else {
        quote! {
            const _: fn() = || {
                #(
                    // This will fail to compile for primitive types, as they do not implement prost::Message
                    fn assert_valid_rpc_type<T: ::prost::Message + ::std::default::Default + 'static>() {}
                    let _ = assert_valid_rpc_type::<#arg_types>;
                )*
            };
        }
    };

    let gen = quote! {
        #output_assert
        #input_assert

        // Original function body moved to an internal implementation
        #impl_fn

        // Public wrapper that adds an Autobahn client and returns a Result
        #vis async fn #original_fn_name(
            #wrapper_params
        ) -> ::std::result::Result<#output_type, #crate_token::rpc::RPCError> {
            let args = #args_handling;

            client.call_rpc::<#output_type, #input_type>(
                #rpc_name.to_string(),
                args,
                timeout_ms,
            ).await
        }
    };

    gen.into()
}

/// Convert a function to an RPC name string with type information
fn from_function_to_rpc_name(func: &syn::ItemFn) -> String {
    use syn::{FnArg, ReturnType, Type};

    let fn_name = func.sig.ident.to_string();

    // Collect parameter type names
    let mut param_types = Vec::new();
    for input in &func.sig.inputs {
        match input {
            FnArg::Typed(pat_type) => {
                let ty = &*pat_type.ty;
                let type_name = match ty {
                    Type::Path(type_path) => type_path
                        .path
                        .segments
                        .last()
                        .map(|seg| seg.ident.to_string())
                        .unwrap_or_else(|| format!("{:?}", ty)),
                    _ => format!("{:?}", ty),
                };
                param_types.push(type_name);
            }
            FnArg::Receiver(_) => {}
        }
    }

    if func.sig.inputs.is_empty() {
        param_types.push("None".to_string());
    }

    // Get return type name
    let return_type = match &func.sig.output {
        ReturnType::Default => "None".to_string(),
        ReturnType::Type(_, ty) => match &**ty {
            Type::Path(type_path) => type_path
                .path
                .segments
                .last()
                .map(|seg| seg.ident.to_string())
                .unwrap_or_else(|| format!("{:?}", ty)),
            _ => format!("{:?}", ty),
        },
    };

    // Match Python: <function name><arg types...><return type>
    format!("{}{}{}", fn_name, param_types.join(""), return_type)
}

/// Check if a type is a primitive type that should be rejected
fn is_primitive_type(ty: &syn::Type) -> bool {
    match ty {
        Type::Path(type_path) => {
            if let Some(segment) = type_path.path.segments.last() {
                let type_name = segment.ident.to_string();
                matches!(
                    type_name.as_str(),
                    "bool"
                        | "i8"
                        | "i16"
                        | "i32"
                        | "i64"
                        | "i128"
                        | "u8"
                        | "u16"
                        | "u32"
                        | "u64"
                        | "u128"
                        | "f32"
                        | "f64"
                        | "char"
                        | "str"
                        | "String"
                )
            } else {
                false
            }
        }
        Type::Reference(type_ref) => {
            // Check if it's &str or similar
            is_primitive_type(&type_ref.elem)
        }
        _ => false,
    }
}
