import asyncio
import logging
import os
import signal
import subprocess

import asyncssh

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Globals to track the server process
server_process = None
server_script = "../ark/start.sh"

ark_banner = """

    _       _     ___              _          _   ___         _            _
   /_\  _ _| |__ / __|_  _ _ ___ _(_)_ ____ _| | | __|_ _____| |_ _____ __| |
  / _ \| '_| / / \__ \ || | '_\ V / \ V / _` | | | _|\ V / _ \ \ V / -_) _` |
 /_/ \_\_| |_\_\ |___/\_,_|_|  \_/|_|\_/\__,_|_| |___|\_/\___/_|\_/\___\__,_|
"""

AUTHORIZED_KEYS_FILE = "authorized_keys"  # Path to the authorized keys file


def is_server_running():
    """Check if the server process is running."""
    return server_process is not None and server_process.poll() is None


async def start_server():
    """Start the server process if it is not already running."""
    global server_process
    if not is_server_running():
        try:
            logging.info("Starting the server process.")
            server_process = subprocess.Popen(
                ["bash", server_script], preexec_fn=os.setsid
            )
            return "Die Kiste läuft jetzt!"
        except Exception as e:
            logging.error(f"Failed to start the server process: {e}")
            return "Fehler beim Start."
    else:
        logging.info("Server is already running.")
        return "Die Kiste läuft doch schon!!!"


async def stop_server():
    """Stop the server process and all child processes more reliably."""
    global server_process
    logging.info("Stopping the server process.")

    try:
        if server_process:
            # Ark Server needs SIGINT two times
            logging.info("Sending SIGINT to process group.")
            os.killpg(os.getpgid(server_process.pid), signal.SIGINT)
            await asyncio.sleep(5)
            os.killpg(os.getpgid(server_process.pid), signal.SIGINT)
            await asyncio.sleep(5)

            if is_server_running():  # if it still running try a more forceful way:
                logging.info("Server did not stop gracefully, trying SIGTERM.")
                os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
                await asyncio.sleep(5)

            if is_server_running():  # if it still running try force kill
                logging.info("Server did not stop with SIGTERM, using SIGKILL.")
                os.killpg(os.getpgid(server_process.pid), signal.SIGKILL)
                await asyncio.sleep(2)

    except ProcessLookupError:
        logging.info("Server process not found, assuming it's stopped.")

    server_process = (
        None  # clear the process if we killed it or the process has shutdown
    )

    if is_server_running():
        logging.error("Server failed to stop.")
        return "Der Server konnte nicht gestoppt werden :|"
    else:
        logging.info("Server stopped.")
        return "OK, Server wurde beendet."


async def handle_ssh_session(process):
    """Handle incoming SSH sessions."""
    process.stdout.write(ark_banner)
    process.stdout.write(
        "      \033[32mALIVE\033[0m\n\n"
        if is_server_running()
        else "      \033[33mDEAD\033[0m\n\n"
    )
    process.stdout.write("Hi, hier kannste den Ark Server managen.\n")
    process.stdout.write("Das kann ich dir anbieten: start, stop, status, exit\n")
    while True:
        process.stdout.write("> ")
        command = await process.stdin.readline()
        if not command:
            break

        command = command.strip()
        if command == "start":
            response = await start_server()
        elif command == "stop":
            if is_server_running():
                process.stdout.write("Ich fahr die Kiste runter, bitte warten...\n")
                response = await stop_server()
            else:
                logging.info("Server is not running.")
                response = "Die Kiste läuft NICHT!!!"
        elif command == "status":
            response = (
                "Die Kiste läuft!" if is_server_running() else "Die Kiste läuft NICHT!"
            )
        elif command == "exit":
            process.stdout.write("Servaas!\n")
            break
        else:
            response = "Das geht nicht. Probiers mit start, stop, status, oder exit."

        process.stdout.write(response + "\n")
    process.exit(0)


async def start_ssh_server():
    """Start the SSH server."""
    await asyncssh.create_server(
        None,
        process_factory=handle_ssh_session,
        host="0.0.0.0",
        port=8888,
        server_host_keys=["ssh_host_key"],
        authorized_client_keys=AUTHORIZED_KEYS_FILE,
    )


if __name__ == "__main__":
    # Generate host keys if they don't exist
    if not os.path.exists("ssh_host_key"):
        os.system("ssh-keygen -t ed25519 -f ssh_host_key -N ''")
        logging.info("Generated SSH host key.")
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(start_ssh_server())
    except (OSError, asyncssh.Error) as exc:
        sys.exit('Error starting server: ' + str(exc))

    loop.run_forever()
