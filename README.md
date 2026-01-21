## Distributed Multi-Room Chat with Leader Election & Timestamps

This project is a simple distributed-style chat application built in Python.

## This project has been made for the course: Distributed Systems in my third year as a computer science student.

---

## Required Summary

### Architecture

- **Client/server** TCP application: a single server (server_projet.py), multiple clients (client_projet.py).
- The server maintains:
  - a table of **connected clients** (clients) with their socket, username, current room, and connection time;
  - a dictionary of **rooms** (rooms): room name → set of sockets;
  - a dictionary of **room leaders** (leaders): room name → leader username.
- Each client belongs to at most **one room** at a time and sends/receives only messages for that room, plus some global notifications.

### Protocol Used

- Each message is a **single UTF-8 text line** terminated by `\n` (very simple text protocol).
- On connection, the client sends **only its username**:
  - `salam\n`
- **Commands** start with `/` and are sent as typed:
  - `/users\n`, `/room\n`, `/join main\n`, `/leader\n`, etc.
- **Chat messages** are plain text lines with no special prefix:
  - `Hello everyone!\n`
- The server returns human-readable, preformatted strings, for example:
  - room chat messages: `[HH:MM:SS] salam: Hello everyone!`
  - room notifications: `[HH:MM:SS] salam joined the room`
  - global leave notifications: `[HH:MM:SS] salam left the room main`
  - command replies: `Leader of room main: salam`, `Users: user1, user2`, etc.

### Technical Choices

- Use of **TCP sockets** and `select.select()` on the server side to manage multiple clients without multithreading.
- On the client side, use of a **dedicated thread for keyboard input** to stay compatible with Windows (where `select()` does not support `stdin`), and `select()` only on the network socket.
- Deliberately **simple, text-based protocol** to make debugging easy (a simple print shows all traffic).
- **Per-room leader** chosen deterministically: the oldest client in the room (field `connected_at`). When a leader leaves the room or disconnects, a new leader is automatically re-elected.

---

It consists of:

- A TCP server: `server_projet.py`
- A terminal client: `client_projet.py`

The server manages multiple chat rooms, tracks connected users, elects a leader per room, and broadcasts timestamped messages.

---

## Features

- **Multi-client chat** over TCP (one server, many clients)
- **Chat rooms** that users can join/leave dynamically with `/join <room>`
- **Per-room leader election** (earliest-connected user in each room)
- **Global notifications** when users leave rooms or disconnect
- **Human-readable timestamps** on all broadcast messages
- **Graceful disconnect** from clients (`exit` command or `Ctrl+C`)
- **Windows-friendly client**: background thread for keyboard input, `select()` only on the socket

---

## Architecture Overview

### Components

- **Server** (`server_projet.py`)
  - Listens on a TCP port (`HOST = "0.0.0.0"`, `PORT = 7777` by default)
  - Maintains:
    - `clients`: map from socket → `{username, room, connected_at}`
    - `rooms`: map from room name → set of sockets
    - `leaders`: map from room name → leader username
  - Broadcasts messages either to a specific room or to all users
  - Elects and re-elects a **leader per room** based on connection time

- **Client** (`client_projet.py`)
  - Connects to the server with a username
  - Sends chat messages typed by the user
  - Supports commands: `/users`, `/room`, `/join <room>`, `/leader`, `exit`
  - Uses a background thread to read from `stdin` and a main loop to receive from the socket

### Communication Model

- **Transport:** TCP sockets
- **I/O multiplexing:**
  - Server: `select.select()` over the listening socket and all client sockets
  - Client: `select.select()` over the **server socket only** + a background thread for keyboard input

Messages are plain UTF-8 text, one per line (terminated by `\n`).

---

## Leader Election (Per Room)

Each room has at most one leader, stored in the `leaders` dictionary.

Policy:

- **Leader = earliest-connected client in that room**

Implementation details:

- Each client record contains `connected_at` (a `time.time()` timestamp).
- When a user joins a room, the server ensures that room has a valid leader.
- When a user leaves a room or disconnects:
  - If they were the leader, the server re-elects a new leader in that room using the earliest `connected_at`.
  - If the room becomes empty, the room and its leader entry are removed.

Clients can query the current leader of their room with:

```text
/leader
```

The server replies:

```text
Leader of room <room>: <username>
```

or, if there is no leader / no room:

```text
No leader (join a room first)
```

---

## User Commands (Client Side)

From the client, you can type:

- `/users` – list all connected users by username.
- `/room` – show which room you are currently in (or none).
- `/join <room>` – join a room (creates it if it does not exist).
  - Example: `/join main`, `/join project1`.
- `/leader` – display the leader of your current room.
- `exit` – disconnect cleanly from the server.
- Any other text – sent as a **chat message** to your current room.

---

## Message Format & Timestamps

### Client → Server

- **On connect**: the client sends a single line with the username:

  ```text
  <username>\n
  Example:  salam\n
  ```

- **Commands**: sent exactly as typed (e.g. `/join main\n`).

- **Chat messages**: plain text (no protocol prefix):

  ```text
  Hello everyone!\n
  ```

### Server → Client

Server messages are simple human-readable strings, already formatted. The important ones are:

- **Welcome message (to the new client only)**

  ```text
  Welcome to the chat server!
  ```

- **Chat messages in a room**

  When a user sends a normal message in a room, the server broadcasts to all _other_ users in that room:

  ```text
  [HH:MM:SS] <username>: <message>
  ```

  For example:

  ```text
  [12:34:56] salam: Hello everyone!
  ```

- **Join/leave notifications**

  When a user joins a room:

  ```text
  [HH:MM:SS] salam joined the room
  ```

  When a user leaves a room (via `/join` to another room) **or disconnects**:

  ```text
  [HH:MM:SS] salam left the room main
  ```

  This is sent to **all connected users**, regardless of room, so everyone sees who left which room.

The client does not do special parsing for these lines; it simply prints them as received, so the timestamps and usernames are visible directly.

---

## Running the Project

### Requirements

- Python 3.7+
- A terminal (PowerShell, cmd, etc.)

No external dependencies are required (only Python standard library).

### 1. Start the Server

From the project directory:

```bash
python server_projet.py
```

You should see log output like:

```text
09:15:21 | INFO | Server started on 0.0.0.0:7777
```

The default configuration in the server:

- `HOST = "0.0.0.0"` (listen on all interfaces)
- `PORT = 7777`

### 2. Start a Client

In a **new** terminal window, from the same directory:

```bash
python client_projet.py <username> <server_ip> <server_port>

Example on the same machine:
python client_projet.py salam 127.0.0.1 7777
```

You should see something like:

```text
Connected to chat as salam. Type 'exit' to exit.
```

### 3. Start Additional Clients

Open more terminals and run the client with different usernames:

```bash
python client_projet.py user1 127.0.0.1 7777
python client_projet.py user2 127.0.0.1 7777
```

You can now chat between all connected clients.

### 4. Exiting

- Type `exit` in the client to disconnect gracefully, or
- Press `Ctrl+C` to trigger a clean exit handler.

The server will log the disconnection and broadcast a system message informing other clients.

---

## Windows Compatibility Notes

On Windows, `select.select()` **cannot** be used with console `stdin` (`sys.stdin`), only with sockets. Attempting to pass `sys.stdin` to `select()` raises:

```text
OSError: [WinError 10038] An operation was attempted on something that is not a socket
```

To remain compatible:

- The client uses a background **thread** to read from `stdin`.
- The main thread only calls `select()` on the socket.
- A shared `running` flag coordinates a graceful shutdown between threads.

This design keeps the client portable and avoids platform-specific hacks.

---

## Possible Extensions

- **Message ordering and history**
  - Store messages on the server and serve history to newly joined clients.

- **Fault tolerance**
  - Add heartbeat messages and automatic removal of unresponsive clients.
  - Promote a backup server or leader in case of server failure (requires more architecture).

- **Security**
  - Add simple authentication.
  - Use TLS sockets instead of plain TCP.

- **UI improvements**
  - Build a graphical or web-based client.

---

## License

This project is intended for educational purposes to illustrate basic distributed-systems concepts (rooms, leader election, socket programming, timestamps) for the distributed-systems module. Use and modify it freely as needed for learning or experimentation.
