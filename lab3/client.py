import socket #пабота с сокетами
import threading #многопоточность
import sys #вывод
import errno #ошибки
import os #выход

def receive_messages(sock): #потоковая функция для чтения и вывода сообщений сервера
    while True:
        try:
            data = sock.recv(1024) #получаем данные
            if not data: 
                print("\n[!] Соединение разорвано сервером.")
                os._exit(0) 
            msg = data.decode('utf-8')
            sys.stdout.write(f"\r{msg}\nВы: ") #выводим сообщение и строку ввода
            sys.stdout.flush()
        except: 
            os._exit(0)

def start_client(): #основная функция
    tcp_sock = None
    while True: 
        print("\n--- Данные сервера ---")
        srv_ip = input("Введите IP сервера: ")
        srv_tcp_p = int(input("Введите порт сервера: "))
        connected = False
        
        while True:
            print("\n--- Ваши локальные настройки ---")
            my_ip = input("Введите ваш локальный IP: ")
            
            if my_ip == srv_ip:
                print("[!] ОШИБКА: Ваш IP совпадает с IP сервера.")
                continue
                
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #проверяем доступен ли айпи, создаем временный сокет
            try:
                test_sock.bind((my_ip, 0)) #берем любой свободный порт тк это проверка
                test_sock.close() #удлаем временный
            except OSError: #если ошибка создания то говорим
                print(f"[!] ОШИБКА IP: {my_ip} недоступен на этом ПК.")
                test_sock.close()
                continue #если все ок то дальше

            my_tcp_p = int(input("Введите ваш локальный порт: "))
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #создаем сокет: семейство айпи4 адресов + тип TCP
            
            try:
                tcp_sock.bind((my_ip, my_tcp_p)) # привязываем сокет к выбранному локальному адресу и порту
                
                try:
                    tcp_sock.connect((srv_ip, srv_tcp_p)) # пробуем подключиться, инициируем рукопожатие
                except Exception:
                    print("[!] Сервер недоступен.")
                    tcp_sock.close()
                    break # Возврат к вводу данных сервера

                try: # проверяем какой ответ пришел от сервера успех или отказ
                    auth_response = tcp_sock.recv(1024).decode('utf-8')
                    if auth_response == "SUCCESS":
                        print("[*] Успешное подключение!")
                        connected = True
                        break # Выход к вводу имени
                    else:
                        # Сюда попадет текст: "[!] ОТКАЗ СЕРВЕРА: Этот IP уже находится в чате."
                        print(f"\n{auth_response}")
                        tcp_sock.close()
                        continue # повторный ввод локального айпи
                except Exception:
                    print("[!] Ошибка при получении авторизации от сервера.")
                    tcp_sock.close()
                    break

            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    print(f"[!] ОШИБКА ПОРТА: Порт {my_tcp_p} уже занят.")
                else:
                    print(f"[!] ОШИБКА: {e}")
                tcp_sock.close()
                continue
                
        if connected: break

    name = input("Ваше имя: ") #если все нормально запрашиваем имя
    tcp_sock.send(f"{name} присоединился к чату.".encode('utf-8'))
                                                                                     #daemon завершится автоамтически при завершении основного потока
    threading.Thread(target=receive_messages, args=(tcp_sock,), daemon=True).start() #функция кот будет выполняться в потоке, передаваемые элементы, 
                                                                                     #старт зыпускает поток
    while True: #отправляем сообщения до выхода
        try:
            text = input("Вы: ")
            if text.lower() == 'exit': break
            tcp_sock.send(f"[{name}]: {text}".encode('utf-8'))
        except: 
            break
            
    tcp_sock.close()
    os._exit(0) 

if __name__ == "__main__":
    try:
        start_client()
    except KeyboardInterrupt:
        os._exit(0)