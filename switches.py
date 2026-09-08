class DispositivoRede:
    def __init__(self, ip: str, hostname: str, ativo: bool):
        self.__ip = ip
        self.__hostname = hostname
        self.__ativo = ativo

    def verificar_status(self):
        if self.__ativo:
            return "o dispositivo está ligado"
        else:
            return "o dispositivo está desligado"

class Servidor(DispositivoRede):
    def __init__(self, ip: str, hostname: str, ativo: bool, sistema_operacional :str):
        super().__init__(ip, hostname, ativo)
        self.__sistema_operacional = sistema_operacional

    def verificar_status(self):
        n = "ONLINE" if self.__ativo else "OFFLINE"
        return f"SERVIDOR {self.__hostname} -- {self.__ip} -- STATUS: {n}"

class Roteador(DispositivoRede):
    def __init__(self, ip: str, hostname: str, ativo: bool, dispositivos_conectados:list):
        super().__init__(ip, hostname, ativo)
        self.__dispositivos_conectados = dispositivos_conectados

    def verificar_status(self):
        n = "ONLINE" if self.__ativo else "OFFLINE"
        return f"ROTEADOR {self.__hostname} -- {self.__ip} -- STATUS: {n}"

class Switch(DispositivoRede):
    def __init__(self, ip: str, hostname: str, ativo: bool, numero_portas :int):
        super().__init__(ip, hostname, ativo)
        self.__numero_portas = numero_portas

    def verificar_status(self):
        n = "ONLINE" if self.__ativo else "OFFLINE"
        return f"SWITCH {self.__hostname} -- {self.__ip} -- STATUS: {n}"

servidor1 = Servidor("192.168.1.10","SRV-01",True,"Windows Server")
servidor2 = Servidor("192.168.1.11","SRV-02",False,"Ubuntu Server")
roteador1 = Roteador("192.168.1.1","RTR-01",True,["SRV-01", "SW-01"])
roteador2 = Roteador("192.168.1.2","RTR-02",True,["SRV-02", "SW-02"])
switch1 = Switch("192.168.1.20","SW-01",True,24)
switch2 = Switch("192.168.1.21","SW-02",False,48)

dispositivos = []