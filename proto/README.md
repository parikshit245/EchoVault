# Protocol definitions

`echovault/node.proto` is the versioned source of truth for Part 5's internal gRPC contract. Regenerate the Python stubs after changing it with `python -m grpc_tools.protoc -I proto/echovault -I proto --python_out=services/node/app/grpc/generated --grpc_python_out=services/node/app/grpc/generated proto/echovault/node.proto`.
