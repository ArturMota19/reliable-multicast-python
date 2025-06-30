import socket
import threading
import json
import time

# Disseminação de mensagens para um grupo de processos distribuídos, de modo que
# todos os processos corretos recebam o mesmo conjunto de mensagens, mesmo na
# ocorrência de falhas de parada (crash) de processos do grupo

class LamportClock:
    def __init__(self):
        self.time = 0

    def tick(self):
        self.time += 1

    def update(self, received_time):
        self.time = max(self.time, received_time) + 1
        
class Process:
    def __init__(self, pid, peers, port):
        self.pid = pid
        self.peers = peers
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', port))
        threading.Thread(target=self.listen).start()

if __name__ == "__main__":
  print("Rodando")


