#!/usr/bin/env python3

import socket
import select
import sys
import signal
import threading

running = True
recv_buffer = ""

# =========================
# Utility
# =========================
def clean_exit(sock):
    global running
    try:
        sock.sendall(b"QUIT\n")
        sock.close()
    except Exception:
        pass
    running = False


# =========================
# Signal handling (Ctrl+C)
# =========================
def handle_sigint(sig, frame):
    clean_exit(client_socket)


signal.signal(signal.SIGINT, handle_sigint)

# =========================
# Argument parsing
# =========================
if len(sys.argv) != 4:
    print("Usage: python client.py <username> <server_ip> <server_port>")
    sys.exit(1)

username = sys.argv[1]
server_ip = sys.argv[2]
server_port = int(sys.argv[3])

# =========================
# Socket setup
# =========================
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_ip, server_port))

# JOIN protocol
client_socket.sendall((username + "\n").encode())

print(f"Connected as {username}")
print("Commands: /users | /leader | /room | /join <room> | quit\n")

# =========================
# Input thread
# =========================
def stdin_loop():
    global running
    while running:
        try:
            text = sys.stdin.readline()
            if not text:
                clean_exit(client_socket)
                break

            text = text.strip()

            if text.lower() == "quit":
                clean_exit(client_socket)
                break

            # Commands go as-is
            if text.startswith("/"):
                client_socket.sendall((text + "\n").encode())
            else:
                # Normal chat message (send raw text, server adds username/time)
                client_socket.sendall((text + "\n").encode())

        except Exception:
            break


input_thread = threading.Thread(target=stdin_loop, daemon=True)
input_thread.start()

# =========================
# Main receive loop
# =========================
while running:
    try:
        readables, _, _ = select.select([client_socket], [], [], 1.0)
    except Exception:
        break

    for src in readables:
        try:
            data = client_socket.recv(1024)
        except Exception:
            running = False
            break

        if not data:
            running = False
            break

        recv_buffer += data.decode()

        # ---------- LINE-BY-LINE TCP PARSING ----------
        while "\n" in recv_buffer:
            line, recv_buffer = recv_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 4)
            msg_type = parts[0]

            # -------------------------
            # System message
            # -------------------------
            if msg_type == "SYS":
                clock = parts[1]
                text = parts[2]
                print(f"[{clock}] SYSTEM: {text}")

            # -------------------------
            # Chat message (Lamport + real time)
            # MSG <lamport> <hh:mm:ss> <sender> <text>
            # -------------------------
            elif msg_type == "MSG" and len(parts) == 5:
                clock = parts[1]
                real_time = parts[2]
                sender = parts[3]
                text = parts[4]

                # If text starts with "MSG ", remove it
                if text.startswith("MSG "):
                    text = text[4:]

                print(f"[{clock} | {real_time}] {sender}: {text}")

            # -------------------------
            # Leader announcement
            # -------------------------
            elif msg_type == "LEADER":
                clock = parts[1]
                leader = parts[2]
                print(f"[{clock}] SYSTEM: {leader} is now the leader ⭐")

            # -------------------------
            # Fallback (plain text from server)
            # -------------------------
            else:
                print(line)

print("\nDisconnected from server.")
sys.exit(0)
