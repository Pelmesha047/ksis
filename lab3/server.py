import socket #пабота с сокетами
import threading #параллельная обработка
import errno #ошибки
import os #выход из  программы

clients = [] #чписок сокетов подключенных клиентов
active_ips = set() #айпи которые есть в чате

def broadcast(message, sender_socket): # рассылка сообщения всем кроме отправителя
    for client in clients:
        if client != sender_socket:
            try:
                client.send(message) #отправка байтовой строки
            except: #если возникает ошибка удаляем клиента (клиент завершил работу, проблема с сетью)
                if client in clients: clients.remove(client)

def handle_tcp_client(client_socket, addr): #обработка клиента в отдельном потоке - получение и рассылка сообщений
    client_ip = addr[0] #айпи клиента
    print(f"Установлено соединение с {addr}")
    
    while True: #до метки FIN   
        try:
            data = client_socket.recv(1024) #прием до 1024 байт
            if not data: break #выход из цикла если клиент вышел
            print(f"[Сообщение от {addr}]: {data.decode('utf-8')}")
            broadcast(data, client_socket) #рассылка
        except: break #выход при ошибке приема
            
    if client_socket in clients: clients.remove(client_socket) #когда клиент выходит удаляем его ланные
    if client_ip in active_ips: active_ips.remove(client_ip)
    client_socket.close()
    print(f"Соединение с {addr} разорвано.")

def start_server(): #основная функция
    while True:
        print("\n--- Настройка Сервера ---")
        srv_ip = input("Введите IP сервера (напр. 127.0.0.1): ")
        tcp_port = int(input("Введите TCP порт для чата: "))
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #создаем сокет: семейство айпи4 адресов + тип TCP
        
        try:
            tcp_sock.bind((srv_ip, tcp_port)) # привязываем сокет к заданным адресу порту
            tcp_sock.listen(5) #ожидаем, храним очередь в 5 соединений (прошли рукопожатие но еще не обработаны)
            tcp_sock.settimeout(1.0) #прерываемся чтобы проверить не нажали ли ктрл С
            break
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                print(f"[!] ОШИБКА: Порт {tcp_port} уже занят другой программой.")
            elif e.errno == errno.EADDRNOTAVAIL:
                print(f"[!] ОШИБКА: IP-адрес {srv_ip} не принадлежит этому компьютеру.")
            else:
                print(f"[!] НЕИЗВЕСТНАЯ ОШИБКА: {e}")
            tcp_sock.close()

    print(f"\n[*] Сервер запущен на {srv_ip}:{tcp_port}! Для выключения: Ctrl+C")

    try:
        while True:
            try:
                client_sock, addr = tcp_sock.accept() #ждем соединения и берем сокет и адрес
            except socket.timeout: #при отсутствии соединения прерываемся на проверку ктрл С
                continue
            
            client_ip = addr[0]
            if client_ip in active_ips: #если такой айпи есть не принимаем
                client_sock.send("[!] ОТКАЗ СЕРВЕРА: Этот IP уже находится в чате.".encode('utf-8'))
                client_sock.close()
                continue

            client_sock.send("SUCCESS".encode('utf-8'))
            active_ips.add(client_ip)
            clients.append(client_sock)
            threading.Thread(target=handle_tcp_client, args=(client_sock, addr), daemon=True).start() #daemon завершится автоамтически при завершении основного потока
                                                                                                      #функция кот будет выполняться в потоке, передаваемые элементы, 
                                                                                                      #старт зыпускает поток
            
    except KeyboardInterrupt:
        print("\n\n[*] Остановка сервера...")
        for client in clients:
            try:
                client.send("\n[СЕРВЕР]: Работа сервера завершена.".encode('utf-8'))
                client.close()
            except: pass
        tcp_sock.close()
        print("[*] Сервер успешно выключен.")
        os._exit(0) 

if __name__ == "__main__":
    start_server()