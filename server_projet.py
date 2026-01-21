import socket
import select
import time

# -----------------------------
# basic tcp chat server with
#  - multiple rooms
#  - per room leader election earliest joiner
#  - simple text commands join users room leader
#  - select based io multiplexing single threaded
# -----------------------------

# bind to all interfaces on a fixed tcp port
HOST = "0.0.0.0"
PORT = 7777

# create a tcp ip socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# allow the server to be restarted quickly reuse address
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# bind the socket to the host port and start listening for connections
server_socket.bind((HOST, PORT))
server_socket.listen()

print(f"{time.strftime('%H:%M:%S')} | INFO | Server started on {HOST}:{PORT}")

# list of all sockets we want select to monitor for readability
# includes the server socket and all connected clients
sockets_list = [server_socket]

# mapping from client socket to metadata about the client
#   username     string name of the user
#   room         current room name or none if not in any
#   connected at timestamp when the user connected used for leader election
clients = {}        # socket to username room connected at

# mapping from room name to set of client sockets currently in that room
rooms = {}          # room name to set of sockets

# mapping from room name to username of current room leader
# leader is the earliest connected user in the room
leaders = {}        # room name to leader username


def broadcast(room, message, sender_socket=None):
    """
    Send a message to all clients in a specific room.

    :param room: name of the room to broadcast to
    :param message: string message (without encoding)
    :param sender_socket: optional socket of the sender (to exclude from send)
    """
    if room not in rooms:
        return

    # iterate over a copy so we can safely remove dead sockets
    for client in list(rooms[room]):
        if client == sender_socket:
            continue
        try:
            client.sendall(message.encode())
        except OSError:
            # client connection is broken -> clean it up
            rooms[room].discard(client)
            if client in sockets_list:
                sockets_list.remove(client)
            if client in clients:
                del clients[client]


def broadcast_global(message, sender_socket=None):
    """
    Send a message to all connected clients, regardless of room.

    :param message: string message (without encoding)
    :param sender_socket: optional socket of the sender (to exclude from send)
    """
    for client in list(clients.keys()):
        if client == sender_socket:
            continue
        try:
            client.sendall(message.encode())
        except OSError:
            # client connection is broken -> clean it up
            if client in sockets_list:
                sockets_list.remove(client)
            del clients[client]


def elect_leader_for_room(room):
    """
    Re-elect a leader for a room after a join/leave/disconnect.

    Policy: earliest-connected client in the room (smallest connected_at).
    If the room becomes empty, remove its leader entry.

    :param room: room name for which to (re-)elect a leader
    :return: username of the elected leader, or None if room is empty
    """
    if room not in rooms or not rooms[room]:
        # no clients left in this room clear any stale leader entry
        if room in leaders:
            del leaders[room]
        return None

    # choose the socket with the oldest connection time
    leader_socket = min(rooms[room], key=lambda s: clients[s]["connected_at"])
    leader_username = clients[leader_socket]["username"]
    # persist the new leader in the leaders dict
    leaders[room] = leader_username
    return leader_username


# main server loop handle new connections and existing client traffic
while True:
    # select waits until at least one socket is ready for reading
    # read_sockets sockets ready to read from
    # exception_sockets sockets with errors
    read_sockets, _, exception_sockets = select.select(
        sockets_list, [], sockets_list
    )

    # handle all sockets that became readable
    for notified_socket in read_sockets:

        # -----------------------------
        # new incoming connection
        # -----------------------------
        if notified_socket == server_socket:
            # accept the new tcp connection creates a new client socket
            client_socket, client_address = server_socket.accept()

            # first message from client is expected to be its username
            username = client_socket.recv(1024).decode().strip()

            # add the new client socket to our monitored list
            sockets_list.append(client_socket)
            # store metadata about this new client
            clients[client_socket] = {
                "username": username,
                "room": None,               # not in any room yet
                "connected_at": time.time() # used for leader election
            }

            ts = time.strftime('%H:%M:%S')
            print(f"{ts} | INFO | New TCP connection from {client_address} ({username})")

            # send an initial welcome message to the client
            client_socket.sendall("Welcome to the chat server!\n".encode())

        # -----------------------------
        # existing client sent data
        # -----------------------------
        else:
            try:
                message = notified_socket.recv(1024).decode().strip()
                if not message:
                    raise Exception("Disconnected")

                user = clients[notified_socket]
                username = user["username"]
                room = user["room"]

                ts = time.strftime('%H:%M:%S')
                print(f"{ts} | RECEIVED | {username}: {message}")

                # --------------------------------------
                # commands messages that start with slash
                # --------------------------------------
                if message.startswith("/"):

                    # users list all connected users
                    if message == "/users":
                        users_list = [clients[c]["username"] for c in clients]
                        notified_socket.sendall(
                            ("Users: " + ", ".join(users_list) + "\n").encode()
                        )

                    # room tell the user which room they are currently in
                    elif message == "/room":
                        if room:
                            notified_socket.sendall(
                                f"You are in room {room}\n".encode()
                            )
                        else:
                            notified_socket.sendall(
                                "You are not in any room\n".encode()
                            )

                    # join room join or create a chat room
                    elif message.startswith("/join"):
                        # everything after join is the room name can include spaces
                        room_name = message[6:].strip()
                        if not room_name:
                            notified_socket.sendall("Usage: /join <room>\n".encode())
                            # skip rest of this iteration user did not specify a room
                            continue

                        new_room = room_name

                        # ----------------------
                        # leave old room if any
                        # ----------------------
                        if room and notified_socket in rooms.get(room, set()):
                            rooms[room].remove(notified_socket)
                            ts = time.strftime('%H:%M:%S')

                            # inform all users that this user left a room
                            # global broadcast not only the old room
                            broadcast_global(
                                f"[{ts}] {username} left the room {room}\n",
                                sender_socket=notified_socket
                            )

                            # if the user was leader re elect a new leader for that room
                            if leaders.get(room) == username:
                                elect_leader_for_room(room)

                            # if the room is now empty clean up its data structures
                            if room in rooms and not rooms[room]:
                                del rooms[room]
                                if room in leaders:
                                    del leaders[room]

                        # ----------------------
                        # join the new room
                        # ----------------------
                        # create room entry if not exists then add client
                        rooms.setdefault(new_room, set()).add(notified_socket)
                        # update clients current room in metadata
                        clients[notified_socket]["room"] = new_room

                        # ensure the new room always has a valid leader
                        elect_leader_for_room(new_room)

                        # confirm to the user
                        notified_socket.sendall(
                            f"You joined room {new_room}\n".encode()
                        )
                        ts = time.strftime('%H:%M:%S')
                        # notify other users in this room that a new user joined
                        broadcast(
                            new_room,
                            f"[{ts}] {username} joined the room\n",
                            notified_socket
                        )

                    # leader show leader of the current room
                    elif message == "/leader":
                        if room and room in leaders:
                            notified_socket.sendall(
                                f"Leader of room {room}: {leaders[room]}\n".encode()
                            )
                        else:
                            notified_socket.sendall(
                                "No leader (join a room first)\n".encode()
                            )

                    # any other slash command is unknown
                    else:
                        notified_socket.sendall(
                            "Unknown command\n".encode()
                        )

                # --------------------------------------
                # normal chat message no leading slash
                # --------------------------------------
                else:
                    # user must be in a room to send regular messages
                    if not room:
                        notified_socket.sendall(
                            "Join a room first using /join <room>\n".encode()
                        )
                    else:
                        ts = time.strftime('%H:%M:%S')
                        # broadcast the chat message to all users in the same room
                        broadcast(
                            room,
                            f"[{ts}] {username}: {message}\n",
                            notified_socket
                        )

            except Exception:
                username = clients[notified_socket]["username"]
                ts = time.strftime('%H:%M:%S')
                print(f"{ts} | INFO | Client {username} disconnected")
                # any exception in receive or processing is treated as a client disconnect
                username = clients[notified_socket]["username"]
                print(f"Client {username} disconnected")

                room = clients[notified_socket]["room"]
                if room and notified_socket in rooms.get(room, set()):
                    # remove client from its room
                    rooms[room].remove(notified_socket)

                    # inform others globally that this user left or disconnected
                    ts = time.strftime('%H:%M:%S')
                    broadcast_global(
                        f"[{ts}] {username} left the room {room}\n",
                        sender_socket=notified_socket
                    )

                    # if this client was the leader of the room re elect
                    if leaders.get(room) == username:
                        elect_leader_for_room(room)

                    # if the room is now empty clean up room and leader
                    if room in rooms and not rooms[room]:
                        del rooms[room]
                        if room in leaders:
                            del leaders[room]

                # remove client from global structures and close socket
                sockets_list.remove(notified_socket)
                del clients[notified_socket]
                notified_socket.close()

    # handle sockets that had an exception errors
    for notified_socket in exception_sockets:
        # for simplicity just remove and close them
        sockets_list.remove(notified_socket)
        notified_socket.close()