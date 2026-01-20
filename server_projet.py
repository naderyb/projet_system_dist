import socket
import select
import time

HOST = "0.0.0.0"
PORT = 7777

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen()

print(f"{time.strftime('%H:%M:%S')} | INFO | Server started on {HOST}:{PORT}")

sockets_list = [server_socket]

clients = {}        # socket -> {username, room, connected_at}
rooms = {}          # room_name -> set of sockets
leaders = {}        # room_name -> leader username


def broadcast(room, message, sender_socket=None):
    if room not in rooms:
        return
    for client in rooms[room]:
        if client != sender_socket:
            client.sendall(message.encode())


def broadcast_global(message, sender_socket=None):
    """Send a message to all connected clients, regardless of room."""
    for client in clients:
        if client != sender_socket:
            client.sendall(message.encode())


def elect_leader_for_room(room):
    """Re-elect leader for a room after join/leave/disconnect.

    Policy: earliest-connected client in the room (smallest connected_at).
    If room becomes empty, remove its leader entry.
    """
    if room not in rooms or not rooms[room]:
        # No clients left in this room
        if room in leaders:
            del leaders[room]
        return None

    # Choose socket with minimum connected_at
    leader_socket = min(rooms[room], key=lambda s: clients[s]["connected_at"])
    leader_username = clients[leader_socket]["username"]
    leaders[room] = leader_username
    return leader_username


while True:
    read_sockets, _, exception_sockets = select.select(
        sockets_list, [], sockets_list
    )

    for notified_socket in read_sockets:

        # New connection
        if notified_socket == server_socket:
            client_socket, client_address = server_socket.accept()

            username = client_socket.recv(1024).decode().strip()
            sockets_list.append(client_socket)
            clients[client_socket] = {
                "username": username,
                "room": None,
                "connected_at": time.time(),
            }

            print(f"{time.strftime('%H:%M:%S')} | INFO | New TCP connection from {client_address} ({username})")

            client_socket.sendall("Welcome to the chat server!\n".encode())

        # Existing client
        else:
            try:
                message = notified_socket.recv(1024).decode().strip()
                if not message:
                    raise Exception("Disconnected")

                user = clients[notified_socket]
                username = user["username"]
                room = user["room"]

                print(f"RECEIVED from {username}: {message}")

                # COMMANDS
                if message.startswith("/"):

                    # /users
                    if message == "/users":
                        users_list = [clients[c]["username"] for c in clients]
                        notified_socket.sendall(
                            ("Users: " + ", ".join(users_list) + "\n").encode()
                        )

                    # /room
                    elif message == "/room":
                        if room:
                            notified_socket.sendall(
                                f"You are in room {room}\n".encode()
                            )
                        else:
                            notified_socket.sendall(
                                "You are not in any room\n".encode()
                            )

                    # /join <room>
                    elif message.startswith("/join"):
                        # Join everything after the command as the room name
                        room_name = message[6:].strip()
                        if not room_name:
                            notified_socket.sendall("Usage: /join <room>\n".encode())
                            continue

                        new_room = room_name

                        # Leave old room
                        if room and notified_socket in rooms.get(room, set()):
                            rooms[room].remove(notified_socket)
                            ts = time.strftime('%H:%M:%S')
                            # Inform everyone that this user left the room
                            broadcast_global(f"[{ts}] {username} left the room {room}\n", sender_socket=notified_socket)

                            # If the leaver was the leader, re-elect
                            if leaders.get(room) == username:
                                elect_leader_for_room(room)

                            # Cleanup empty room
                            if room in rooms and not rooms[room]:
                                del rooms[room]
                                if room in leaders:
                                    del leaders[room]

                        # Join new room
                        rooms.setdefault(new_room, set()).add(notified_socket)
                        clients[notified_socket]["room"] = new_room

                        # Ensure the new room always has a valid leader
                        elect_leader_for_room(new_room)

                        notified_socket.sendall(
                            f"You joined room {new_room}\n".encode()
                        )
                        ts = time.strftime('%H:%M:%S')
                        broadcast(new_room, f"[{ts}] {username} joined the room\n", notified_socket)

                    # /leader
                    elif message == "/leader":
                        if room and room in leaders:
                            notified_socket.sendall(
                                f"Leader of room {room}: {leaders[room]}\n".encode()
                            )
                        else:
                            notified_socket.sendall(
                                "No leader (join a room first)\n".encode()
                            )

                    else:
                        notified_socket.sendall(
                            "Unknown command\n".encode()
                        )

                # NORMAL MESSAGE
                else:
                    if not room:
                        notified_socket.sendall(
                            "Join a room first using /join <room>\n".encode()
                        )
                    else:
                        ts = time.strftime('%H:%M:%S')
                        broadcast(
                            room,
                            f"[{ts}] {username}: {message}\n",
                            notified_socket
                        )

            except Exception:
                username = clients[notified_socket]["username"]
                print(f"Client {username} disconnected")

                room = clients[notified_socket]["room"]
                if room and notified_socket in rooms.get(room, set()):
                    rooms[room].remove(notified_socket)

                    # Inform everyone that this user left the room / disconnected
                    ts = time.strftime('%H:%M:%S')
                    broadcast_global(f"[{ts}] {username} left the room {room}\n", sender_socket=notified_socket)

                    # If this client was the leader of the room, re-elect
                    if leaders.get(room) == username:
                        elect_leader_for_room(room)

                    # Cleanup empty room structures
                    if room in rooms and not rooms[room]:
                        del rooms[room]
                        if room in leaders:
                            del leaders[room]

                sockets_list.remove(notified_socket)
                del clients[notified_socket]
                notified_socket.close()

    for notified_socket in exception_sockets:
        sockets_list.remove(notified_socket)
        notified_socket.close()