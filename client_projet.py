# interactive tcp chat client for the distributed systems project
# responsibilities
#   - connect to the chat server and register the chosen username
#   - run a background thread that reads from stdin and sends data to the server
#   - receive and parse line based protocol messages from the server
#       * sys    system or informational messages
#       * msg    normal chat messages with logical and real clocks
#       * leader  notifications about the current room leader
#   - handle clean shutdown when the user types exit or presses ctrlc
import socket
import select
import sys
import signal
import threading

# global flag used by both the stdin thread and the main receive loop
# when set to false all loops exit and the process terminates
running = True
# string buffer that accumulates raw data from the socket until full lines
# terminated by n are available for parsing
recv_buffer = ""

# =========================
# utility
# =========================
def clean_exit(sock):
    """Close the connection to the server and stop the client loops."""
    global running
    try:
        # inform the server that this client is exitting
        # the protocol does not depend on this so failures are ignored
        sock.sendall(b"exit\n")
        sock.close()
    except Exception:
        # any error during shutdown can be silently ignored
        pass
    # signal both the stdin thread and the receive loop to stop
    running = False


# =========================
# signal handling ctrlc
# =========================
def handle_sigint(sig, frame):
    """
    Handle SIGINT (Ctrl+C) by performing the same clean shutdown
    as the "exit" command.
    """
    clean_exit(client_socket)


signal.signal(signal.SIGINT, handle_sigint)

# =========================
# argument parsing
# =========================
# expect exactly three arguments
#   1 username used to identify this client to the server
#   2 server ip or hostname of the chat server
#   3 server port tcp port number of the chat server
if len(sys.argv) != 4:
    print("Usage: python client.py <username> <server_ip> <server_port>")
    sys.exit(1)

username = sys.argv[1]
server_ip = sys.argv[2]
server_port = int(sys.argv[3])

# =========================
# socket setup
# =========================
# create a tcp socket and connect it to the server
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_ip, server_port))

# join protocol send the username terminated by a newline so the server
# can associate the socket with this user
client_socket.sendall((username + "\n").encode())

print(f"Connected as {username}")
print("Commands: /users | /leader | /room | /join <room> | exit\n")

# =========================
# input thread
# =========================
def stdin_loop():
    """
    Read user input from stdin in a separate thread and forward it
    to the server as either commands (starting with '/') or normal
    chat messages.
    """
    global running
    while running:
        try:
            # blocking read from stdin returns an empty string on eof
            text = sys.stdin.readline()
            if not text:
                # eof for example terminal closed shut down the client
                clean_exit(client_socket)
                break

            # remove trailing newline and surrounding whitespace
            text = text.strip()

            # local exit keyword does not go to the server as a message
            if text.lower() == "exit":
                clean_exit(client_socket)
                break

            # commands starting with slash are forwarded verbatim
            if text.startswith("/"):
                client_socket.sendall((text + "\n").encode())
            else:
                # normal chat message the server is responsible for
                # adding timestamps and the sender name
                client_socket.sendall((text + "\n").encode())

        except Exception:
            # any error for example socket closed ends the input loop
            break


# run the stdin loop in a background daemon thread so the main thread
# can focus on receiving and printing server messages
input_thread = threading.Thread(target=stdin_loop, daemon=True)
input_thread.start()

# =========================
# main receive loop
# =========================
# the main thread waits for data from the server and parses it line by line
while running:
    try:
        # use select with a timeout to periodically check the running flag
        # only the client socket is monitored for readability
        readables, _, _ = select.select([client_socket], [], [], 1.0)
    except Exception:
        # if select fails for example socket closed exit the loop
        break

    for src in readables:
        try:
            # receive up to 1024 bytes from the server
            data = client_socket.recv(1024)
        except Exception:
            running = False
            break

        if not data:
            # an empty read means the server closed the connection
            running = False
            break

        # append newly received text to the buffer
        recv_buffer += data.decode()

        # line by line tcp parsing
        # process all complete lines currently present in the buffer
        while "\n" in recv_buffer:
            # split off one line up to the first newline
            line, recv_buffer = recv_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                # ignore empty lines
                continue

            # split the message into at most 5 parts so that the payload
            # text can contain spaces without being broken up
            parts = line.split(" ", 4)
            msg_type = parts[0]

            # system message
            # format sys clock text
            if msg_type == "SYS":
                clock = parts[1]
                text = parts[2]
                print(f"[{clock}] SYSTEM: {text}")

            # chat message lamport and real time
            # format from server
            #   msg lamport hhmmss sender text
            elif msg_type == "MSG" and len(parts) == 5:
                clock = parts[1]       # logical clock (e.g., Lamport)
                real_time = parts[2]   # human-readable time from server
                sender = parts[3]      # username of message sender
                text = parts[4]        # message content (may contain spaces)

                # some servers might prepend msg inside text strip it if present
                if text.startswith("MSG "):
                    text = text[4:]

                print(f"[{clock} | {real_time}] {sender}: {text}")

            # leader announcement
            # format leader clock username
            elif msg_type == "LEADER":
                clock = parts[1]
                leader = parts[2]
                print(f"[{clock}] SYSTEM: {leader} is now the leader ⭐")

            # fallback plain text from server
            # for messages that do not follow the structured protocol
            else:
                print(line)

print("\nDisconnected from server.")
sys.exit(0)
