import asyncio
import json
import logging
import signal
import sys
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


def on_signals(cleanup_func: Callable[[], None]) -> None:
    """Setup signal handlers"""

    def signal_handler(sig, frame):
        logger.info(f"Received signal: {sig}")
        if cleanup_func:
            cleanup_func()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def stdio_to_ws(server_name:str, stdio_cmd: str) -> None:
    """Main function that implements stdio to WebSocket forwarding"""
    import ssl

    # Destructure arguments


    # Create async subprocess
    proc = None
    is_ready = False
    child_queue = asyncio.Queue()  # For storing output read from subprocess

    async def cleanup():
        """Function to clean up resources"""
        if proc:
            try:
                proc.terminate()
                await proc.wait()
                logger.info("Subprocess terminated")
            except Exception as err:
                logger.error(f"Error terminating subprocess: {str(err)}")

        await gateway_client.close()

    # Set up signal handling
    on_signals(lambda: asyncio.run(cleanup()))

    try:
        # 1. Start subprocess using asyncio
        logger.info(f"Starting subprocess: {stdio_cmd}")

        # Use async subprocess
        proc = await asyncio.create_subprocess_shell(
            stdio_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
        )

        logger.info(f"Subprocess started, PID: {proc.pid}")

        # 2. Define subprocess to gateway forwarding function
        async def read_stdout():
            """Read from subprocess stdout and parse JSON messages"""
            logger.info("Starting to read from subprocess stdout...")

            buffer = b""  # Use bytes buffer instead of string
            while True:
                try:
                    # Non-blocking read from subprocess output
                    chunk = await proc.stdout.read(1024)
                    if not chunk:  # EOF
                        if proc.returncode is not None:
                            logger.info(
                                f"Subprocess terminated, return code: {proc.returncode}"
                            )
                        else:
                            logger.info(
                                "Subprocess stdout closed but process still running"
                            )
                        break

                    buffer += chunk

                    # Process complete lines
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line:
                            continue

                        # Try to decode with error handling
                        try:
                            line_str = line.decode("utf-8", errors="replace")
                            line_str = line_str.strip()

                            logger.debug(f"Subprocess raw output: {line_str}")

                            if line_str:
                                try:
                                    json_msg = json.loads(line_str)
                                    logger.info(
                                        f"Subprocess → Gateway: {json.dumps(json_msg)[:100]}..."
                                    )
                                    await child_queue.put(json_msg)
                                except json.JSONDecodeError:
                                    logger.error(
                                        f"Subprocess non-JSON output: {line_str}"
                                    )
                        except UnicodeDecodeError as ude:
                            logger.warning(
                                f"Cannot decode as UTF-8: {str(ude)}. Skipping binary data."
                            )

                except Exception as e:
                    logger.error(f"Error reading subprocess output: {str(e)}")
                    await asyncio.sleep(0.1)

            logger.info("Subprocess stdout reading task ended")

        # 3. Monitor subprocess error output
        async def read_stderr():
            """Read content from subprocess stderr"""
            logger.info("Starting to monitor subprocess error output...")

            while True:
                try:
                    chunk = await proc.stderr.read(1024)
                    if not chunk:  # EOF
                        if proc.returncode is not None:
                            logger.info(
                                f"Subprocess terminated, return code: {proc.returncode}"
                            )
                        else:
                            logger.info(
                                "Subprocess stderr closed but process still running"
                            )
                        break

                    # Use error handling when decoding
                    text = chunk.decode("utf-8", errors="replace").strip()
                    if text:
                        for line in text.split("\n"):
                            if line.strip():
                                logger.info(f"Subprocess stderr: {line.strip()}")

                except Exception as e:
                    logger.error(f"Error reading subprocess error output: {str(e)}")
                    await asyncio.sleep(0.1)

            logger.info("Subprocess error output monitoring task ended")

        # 4. Process subprocess output in queue and forward to gateway
        async def process_child_output():
            """Process subprocess output in queue and forward to gateway"""
            logger.info("Starting to process subprocess output queue...")

            while True:
                try:
                    json_msg = await child_queue.get()
                    logger.info(
                        f"Processing subprocess queue message: {json.dumps(json_msg)}..."
                    )

                    await gateway_client.send(json_msg)
                    child_queue.task_done()
                except Exception as e:
                    logger.error(f"Error processing subprocess output queue: {str(e)}")
                    await asyncio.sleep(0.1)

        # 5. Define gateway to subprocess message handling
        async def forward_gateway_to_child(message: Any, _: Optional[str]):
            """Forward gateway messages to subprocess"""
            if proc and proc.stdin:
                message_str = json.dumps(message)
                logger.info(f"Gateway → Subprocess: {message_str}...")
                try:
                    # Ensure message ends with newline
                    if not message_str.endswith("\n"):
                        message_str += "\n"

                    proc.stdin.write(message_str.encode("utf-8"))
                    await proc.stdin.drain()
                    logger.debug("Message successfully written to subprocess stdin")
                except Exception as e:
                    logger.error(f"Error writing message to subprocess: {str(e)}")

        # 6. Register message handler
        gateway_client.add_message_handler("forward_to_child", forward_gateway_to_child)

        # 7. Start subprocess I/O handling tasks
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        queue_task = asyncio.create_task(process_child_output())


        # 9. Set server state to ready
        is_ready = True


        # 11. After gateway connection ends, cancel all subtasks
        for task in [stdout_task, stderr_task, queue_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task cancelled: {task.get_name()}")

        # 12. Clean up resources
        await cleanup()

    except Exception as err:
        logger.error(f"Startup failed: {str(err)}")
        import traceback

        logger.error(traceback.format_exc())
        await cleanup()
        sys.exit(1)