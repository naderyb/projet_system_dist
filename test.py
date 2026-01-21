import socket
import threading
import time

# address and port of the chat server we are testing
# the script assumes a tcp server is already running and listening here
HOST = "127.0.0.1"
PORT = 7777

# name of the room that both test clients will join
ROOM = "test_room"


def client(name: str, message: str, barrier: threading.Barrier):
    """
    simulate a single chat client
    connects to the server
    sends its username
    joins a specific room
    waits at a barrier so that multiple clients send messages at almost the same time
    sends one message and then closes the connection
    """
    # create a tcp ip socket using ipv4
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))

    # send username to the server
    # the server is expected to read a username terminated by a newline
    s.sendall((name + "\n").encode())

    # try to receive an optional welcome message from the server
    # if the server does not send anything or closes we ignore the error
    try:
        s.recv(1024)  # welcome
    except Exception:
        pass

    # join a specific chat room
    # the protocol here expects a command like join room name
    s.sendall((f"/join {ROOM}\n").encode())

    # try to receive a confirmation such as you joined room
    # again we ignore any errors to keep the test simple
    try:
        s.recv(1024)  # "You joined room..."
    except Exception:
        pass

    # synchronize with other clients
    # the barrier ensures that multiple client threads pause here
    # until all of them have reached this point once the required
    # number of threads parties has called barrier wait they are
    # all released at the same time this allows us to simulate
    # concurrent message sending
    barrier.wait()

    # after the barrier is released send the actual message for this client
    s.sendall((message + "\n").encode())

    # give the server a small amount of time to process the message
    # before we close the socket this avoids closing immediately
    # which could cause the server to miss data in some implementations
    time.sleep(0.5)

    # close the connection cleanly
    s.close()


if __name__ == "__main__":
    # create a barrier for exactly 2 client threads
    # each client will call barrier wait and they will only proceed
    # once both have reached that point
    barrier = threading.Barrier(2)

    # create the first test client thread representing user user1
    # it will connect join the room wait at the barrier and then send its message
    t1 = threading.Thread(
        target=client,
        args=("user1", "hello from user1", barrier),
        daemon=True,  # mark as daemon so it will not block process exit if something goes wrong
    )

    # create the second test client thread representing user user2
    t2 = threading.Thread(
        target=client,
        args=("user2", "hello from user2", barrier),
        daemon=True,
    )

    # start both client threads they will run in parallel
    t1.start()
    t2.start()

    # wait for both threads to finish before exiting the script
    # this ensures both clients have completed their interaction with the server
    t1.join()
    t2.join()