import socket
import threading
import json
import time
import sys

# Disseminação de mensagens para um grupo de processos distribuídos, de modo que
# todos os processos corretos recebam o mesmo conjunto de mensagens, mesmo na
# ocorrência de falhas de parada (crash) de processos do grupo

# O lamport clock serve para sincronizar os processos distribuídos
class LamportClock:
    def __init__(self):
        self.time = 0

    def tick(self):
        self.time += 1

    def update(self, received_time):
        self.time = max(self.time, received_time) + 1

# Crio o processo que vai receber e enviar as mensagens        
class Process:
    def __init__(self, pid, peers, port):
        self.pid = pid
        self.peers = peers
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', port))
        threading.Thread(target=self.listen).start()
        
    def send(self, msg):
        self.clock.tick() # tickando o tempo do processo
        message = json.dumps({ # criando o objeto da mensagem que vou enviar
            'pid': self.pid,
            'time': self.clock.time,
            'msg': msg
        }).encode()
        for peer in self.peers: # enviando a mensagem para peers
            self.sock.sendto(message, ('localhost', peer))
            
    def listen(self):
        while True:
            data, addr = self.sock.recvfrom(1024) # recebendo a mensagem
            message = json.loads(data.decode()) # decodificando a mensagem recebida
            self.clock.update(message['time'])  # atualizando o relógio Lamport
            print(f"O processo {self.pid} recebeu a msg: {message['msg']} de {addr[1]} no tempo {self.clock.time}")
            
if __name__ == "__main__":
  print("Rodando")
  peers = [('localhost', 10001), ('localhost', 10002), ('localhost', 10003)]
  print(sys.argv)
  idx = int(sys.argv[1])
  process = Process(idx + 1, peers[:idx] + peers[idx+1:], peers[idx][1])

  while True:
      msg = input(f"[P{idx+1}] Digite uma mensagem: ")
      process.send(msg)


