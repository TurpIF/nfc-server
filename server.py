import sys
import json
from shm import shm
import threading
import time
import signal
from subprocess import Popen, PIPE
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint as ServerEndpoint

class Card(object):
    def __init__(self):
        self.detected = False
        self.uid = None

class Protocol(protocol.Protocol):
    def __init__(self, shm_card):
        self.shm_card = shm_card

    def send(self, obj):
        self.transport.write(json.dumps(obj) + '\n')
        self.transport.flush()

    def error(self):
        self.send({ 'success': False })

    def dataReceived(self, data):
        try:
            json_data = json.loads(data)
        except ValueError:
            self.error()
            return

        if not 'code' in json_data:
            self.error()
            return

        c = json_data['code']
        if c == 'detected':
            self.detected()
        else:
            self.error()

    def detected(self):
        d = self.shm_card.data
        if not d.detected:
            self.send({
                'success': True,
                'detected': False })
        else:
            self.send({
                'success': True,
                'detected': True,
                'uid': d.uid })

class Factory(protocol.Factory):
    def __init__(self, shm_card):
        self.shm_card = shm_card

    def buildProtocol(self, addr):
        return Protocol(self.shm_card)

class NFC(threading.Thread):
    def __init__(self, shm_card):
        super(NFC, self).__init__()
        self.shm_card = shm_card
        self.nfc_proc = None
        self.running = False

    def start(self):
        assert self.nfc_proc is None
        self.nfc_proc = Popen('./card_polling', stdout=PIPE)
        self.running = False
        super(NFC, self).start()

    def run(self):
        while self.running:
            line = self.nfc_proc.stdout.readline().strip()
            if line == 'No card or Tag detected':
                self.shm_card.data.detected = False
            elif line[:5] == 'UID: ':
                self.shm_card.acquire()
                self.shm_card.get(lock=False).detected = True
                self.shm_card.get(lock=False).uid = line[5:]
                self.shm_card.release()
            time.sleep(0.5)

    def stop(self):
        self.running = False
        if self.nfc_prc is not None:
            self.nfc_proc.terminate()
            self.nfc_proc = None

if __name__ == '__main__':
    PORT = 42420

    card = shm(Card())
    nfc = NFC(card)
    endpoint = ServerEndpoint(reactor, PORT)
    endpoint.listen(Factory(card))

    def sig_handler(signum, frame):
        nfc.stop()
        nfc.join(1)
        reactor.stop()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    nfc.start()
    reactor.run()
