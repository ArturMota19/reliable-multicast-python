import socket
import threading
import json
import time
import sys
try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None  # fallback se nenhum estiver disponível

import builtins


# Definicoes para imprimir no console e capturar mensagem
print_lock = threading.Lock()
original_print = print
prompt_template = "[P{}] Digite uma mensagem (ou ENTER para esperar): "

# Disseminação de mensagens para um grupo de processos distribuídos, de modo que
# todos os processos corretos recebam o mesmo conjunto de mensagens, mesmo na
# ocorrência de falhas de parada (crash) de processos do grupo


# Custom safe_print que respeita o input()
def safe_print(*args, **kwargs):
    with print_lock:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        original_print(*args, **kwargs)
        if readline:
            try:
                line = readline.get_line_buffer()
                prompt = prompt_template.format(sys.argv[1])
                sys.stdout.write(f"\r{prompt}{line}")
                sys.stdout.flush()
            except Exception:
                pass


builtins.print = safe_print

# O lamport clock serve para sincronizar os processos distribuídos
class LamportClock:
    def __init__(self):
        self.time = 0

    def tick(self):
        self.time += 1
        return self.time

    def update(self, received_time):
        self.time = max(self.time, received_time) + 1
        return self.time

# Crio o processo que vai receber e enviar as mensagens
class Process:
    def __init__(self, pid, peers, port):
        self.pid = pid
        self.peers = peers
        self.port = port
        self.clock = LamportClock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', port))
        self.received = set()
        self.sent_buffer = {}  # msg_id -> (message, timestamp, acks)
        self.retransmission_timeout = 3
        self.retransmission_interval = 1.5  # evita flood de retrasmissao
        self.process_count = len(peers) + 1
        self.lock = threading.Lock()

        # A ideia de usar threads eh para garantir que essas funcoes nao vao bloquear o codigo principal, garantindo entrega confiavel

        threading.Thread(target=self.listen, daemon=True).start() # cria thread que vai executar o self.listen
        threading.Thread(target=self.retransmit_loop, daemon=True).start() #cria thread que vai executar o self.retransmit_loop

    def send(self, msg):
        current_time = self.clock.tick() # tickando o tempo do processo
        msg_id = f"{self.pid}-{current_time}"
        message_obj = {     # criando o objeto da mensagem que vou enviar
            'type': 'message',
            'pid': self.pid,
            'time': current_time,
            'msg_id': msg_id,
            'msg': msg
        }
        message = json.dumps(message_obj).encode()

        with self.lock:
            self.sent_buffer[msg_id] = { # armazenando mensagens que ja foram enviadas
                'message': message,
                'acks': set([self.pid]),
                'timestamp': time.time(),
                'last_sent': time.time()
            }

        for peer_port in self.peers:
            self.sock.sendto(message, ('localhost', peer_port)) # enviando msg para os peers
        print(f"[P{self.pid} | t={current_time}] Enviou '{msg}'")

    def listen(self):
        while True:
            data, addr = self.sock.recvfrom(1024) # aguarda mensagem UDP no socket
            message = json.loads(data.decode()) # decodifica os bytes recebidos
            msg_type = message.get('type', 'message') # verifica o tipo da mensagem recebida (ACK ou message)

            if msg_type == 'message': # Tipo message
                updated_time = self.clock.update(message['time']) # atualiza o relogio de Lamport local
                msg_id = message['msg_id']
                if msg_id not in self.received: # garante que a mensagem nao seja processada duas vezes
                    self.received.add(msg_id) # marca como recebida
                    print(f"[P{self.pid} | t={updated_time}] Recebeu '{message['msg']}' de P{message['pid']}")
                    self.send_ack(msg_id) # envia ACK para todos os peers informando que recebeu
            elif msg_type == 'ack': # Tipo ACK
                msg_id = message['msg_id'] # verifica qual mensagem esta sendo confirmada
                sender = message['from'] # identifica quem esta mandando o ACK
                with self.lock: # trava para que dois threads nao alterem sent_buffer ao mesmo tempo
                    if msg_id in self.sent_buffer: # verifica se o processo ainda esta esperando ACK dessa mensagem
                        self.sent_buffer[msg_id]['acks'].add(sender) # se sim, adiciona o sender a lista de ACKs recebidos
                        print(f"[P{self.pid} | t={self.clock.time}] Recebeu ACK de P{sender} para {msg_id}") # mostra no terminal que recebeu o ACK de uma determinada mensagem

    def send_ack(self, msg_id): # criando o retorno de ack para confirmar recebimento de mensagem
        ack = json.dumps({
            'type': 'ack',
            'from': self.pid,
            'msg_id': msg_id
        }).encode()
        for peer_port in self.peers:
            self.sock.sendto(ack, ('localhost', peer_port)) # envia ACK para os peers
        self.sock.sendto(ack, ('localhost', self.port))

    def retransmit_loop(self): # Criando toda a logica de retrasmissao
        while True:
            time.sleep(1) # para evitar varreduras o tempo todo
            now = time.time() # usado para calcular ha quanto tempo a mensagem foi enviada ou retransmitida
            with self.lock: # evita que duas threads alterem o sent_buffer ao mesmo tempo
                for msg_id in list(self.sent_buffer): # passa por todas as mensagens que ainda nao foram confirmadas por todos os peers
                    info = self.sent_buffer[msg_id]
                    if len(info['acks']) >= self.process_count: # verfica se todos os processos ja enviaram um ACK para essa mensagem
                        del self.sent_buffer[msg_id] # se sim, remove do buffer, pois ja foi entregue com sucesso
                        continue
                    if now - info['last_sent'] >= self.retransmission_interval and now - info['timestamp'] >= self.retransmission_timeout: # verifica se ja passou tempo suficiente desde o ultimo envio e desde o envio original
                        for peer_port in self.peers:
                            self.sock.sendto(info['message'], ('localhost', peer_port)) # reenvia a mensagem original para cada peer (em caso de falha ou perda de ACK)
                        print(f"[P{self.pid} | t={self.clock.time}] Retransmitindo {msg_id}")
                        info['last_sent'] = now # atualiza o tempo do ultimo envio da mensagem

if __name__ == "__main__":
    peers = [('localhost', 10001), ('localhost', 10002), ('localhost', 10003)] # definindo lista fixa de peers que vao participar
    idx = int(sys.argv[1]) # le o indice do processo atual da linha de comando (ex: python 3 process.py 1, o idx sera 1)
    process = Process(idx + 1, [p[1] for i, p in enumerate(peers) if i != idx], peers[idx][1]) # criando o processo

    while True:
        try:
            msg = input(prompt_template.format(idx + 1)).strip() # le o input do usuario, removendo os espacos em branco nas bordas
            if msg:
                process.send(msg) # so envia se algo for digitado
        except KeyboardInterrupt: # Criando forma de interrupcao
            print("\nEncerrando processo.")
            break


