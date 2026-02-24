#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/packages/derisk-app/src:$(pwd)/packages/derisk-core/src:$(pwd)/packages/derisk-serve/src:$(pwd)/packages/derisk-ext/src:$(pwd)/packages/derisk-client/src
echo "Starting server with PYTHONPATH=$PYTHONPATH"
nohup python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/my/dev-1.toml > server.log 2>&1 &
echo "Server started with PID $!"
