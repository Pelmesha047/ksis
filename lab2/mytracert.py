import socket # работа с сокетами - отправка/получение пакетов, преобразоваие имен
import struct # формирование заголовков icmp
import time # генерация времени отправки и получения, идентификатора пакета
import select # ожидание ответа
import argparse # разбор аргументов командной строки

# Константы для ICMP протокола - типы сообщений
ICMP_ECHO_REQUEST = 8 # эхо запрос
ICMP_ECHO_REPLY = 0 # эхо ответ
ICMP_TIME_EXCEEDED = 11 # истечение времени работы пакета

def calculate_checksum(data):
    """Расчет контрольной суммы ICMP-пакета"""
    checksum = 0
    # последовательность байт разбивается на 16 битные числа (2 байта)
    count_to = (len(data) // 2) * 2 #определяем сколько пар
    for count in range(0, count_to, 2):
        this_val = data[count + 1] * 256 + data[count]
        checksum += this_val
        checksum &= 0xffffffff # сумма накапливается в переменной с маской
    
    # Если остался 1 нечетный байт, то добавляем его как младший байт (старший считается нулём)
    if count_to < len(data):
        checksum += data[-1]
        checksum &= 0xffffffff
        
    # Складываем переполнения. берём старшие 16 бит и складываем с младшими 16 битами, повторяем, пока не останется только младшие 16 бит
    checksum = (checksum >> 16) + (checksum & 0xffff)
    checksum += (checksum >> 16)
    
    # Инвертируем результат и берём младшие 16 бит
    answer = ~checksum & 0xffff
    return answer >> 8 | (answer << 8 & 0xff00) #если на хосте литл эндиан то меняем байты местами

def create_icmp_packet(packet_id, sequence):
    """Создает бинарный ICMP Echo Request пакет."""
    # Переводим ID и Sequence в сетевой порядок байтов (Big Endian)
    net_packet_id = socket.htons(packet_id)
    net_sequence = socket.htons(sequence)

    # Создаем пустой заголовок (без чексуммы). 
    # Используем "bbHHH" чтобы числа поместились b – signed char (1 байт) H – unsigned short (2 байта)
    header = struct.pack("bbHHH", ICMP_ECHO_REQUEST, 0, 0, net_packet_id, net_sequence)
    data = struct.pack("d", time.time()) #время отправки записываем 8 байт
    
    # Считаем чексумму для связки заголовок + данные
    my_checksum = calculate_checksum(header + data)
    
    # Пересобираем заголовок уже с правильной контрольной суммой
    header = struct.pack("bbHHH", ICMP_ECHO_REQUEST, 0, socket.htons(my_checksum), net_packet_id, net_sequence)
    
    return header + data

def get_node_name(ip_address, resolve_names):
    """Пытается получить доменное имя узла по IP, если включен флаг -n."""
    if not resolve_names:
        return ip_address
    try:
        host_name = socket.gethostbyaddr(ip_address)[0]
        return f"{host_name} [{ip_address}]"
    except (socket.herror, socket.gaierror):
        return ip_address

def run_traceroute(target_host, resolve_names=False, max_hops=30, timeout=2.0):
    """Основная логика трассировки маршрута."""
    try:
        dest_addr = socket.gethostbyname(target_host) #получаем айпи адрес целевого узла
    except socket.gaierror:
        print(f"Ошибка: Не удается разрешить имя {target_host}")
        return

    print(f"Трассировка маршрута к {target_host} [{dest_addr}]\nмаксимальное число прыжков: {max_hops}\n")

    icmp_proto = socket.getprotobyname("icmp") #заголовок трассировки, номер протокола
    packet_id = int(time.time()) & 0xFFFF #уникальный идентификатор пакетов
    sequence = 0 #счетчик отправленных пакетов 
    target_reached = False #доступность конечного узла

    try:
        # Создаем сокет
        # Менеджер 'with' закроет сокет в конце
        with socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp_proto) as my_socket:
            my_socket.bind(("", 0)) #привязывает сокет к локальному адресу и прроизвольному порту
            
            # Проходим по значениям TTL (от 1 до max_hops)
            for ttl in range(1, max_hops + 1):
                # Обновляем TTL на существующем сокете
                my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl) # задает значение ттл
                print(f"{ttl:>2}\t", end="", flush=True) #печатаем номер шага
                
                curr_node_ip = None #хранит айпи адрес узла ответившего на пакет

                # Отправляем 3 пакета для каждого TTL
                for _ in range(3):
                    sequence += 1
                    packet = create_icmp_packet(packet_id, sequence) #создаем пакет
                    send_time = time.time() #запоминаем время отправки
                    
                    my_socket.sendto(packet, (dest_addr, 1)) #отправляем на целевой адрес
                    
                    # Ждем ответа
                    while True:
                        ready = select.select([my_socket], [], [], timeout)
                        if not ready[0]: # Если таймаут
                            print("* \t", end="", flush=True)
                            break
                        
                        recv_time = time.time() #запоминаем время получения и айпи отправителя
                        packet_data, addr = my_socket.recvfrom(1024) #получает пакет и адрес отправителя
                        curr_node_ip = addr[0]
                        
                        # Достаем ICMP-заголовок (пропуская IP-заголовок)
                        iph_length = (packet_data[0] & 0xF) * 4 
                        icmp_header = packet_data[iph_length:iph_length + 8] #8 байт после айпи заголовка
                        icmp_type, _, _, _, _ = struct.unpack("bbHHH", icmp_header) #распаковка
                        
                        # Если это нужный нам ответ — вычисляем ртт печатаем значение
                        if icmp_type in (ICMP_TIME_EXCEEDED, ICMP_ECHO_REPLY):
                            rtt = (recv_time - send_time) * 1000
                            print(f"{rtt:>3.0f} мс\t", end="", flush=True)
                            if icmp_type == ICMP_ECHO_REPLY: # если это эхо реплай то узел конечный устанавливаем флаг
                                target_reached = True
                            break # Пакет получен, идем к следующему из 3-х

                # Выводим имя/IP узла после 3-х попыток если хотя бы один пакет был получен
                if curr_node_ip:
                    print(f" {get_node_name(curr_node_ip, resolve_names)}")
                else:
                    print(" Превышен интервал ожидания.")
                    
                # Если дошли до цели — завершаем работу
                if target_reached:
                    print("\nТрассировка завершена.")
                    break

    except PermissionError: #если без прав администратора
        print("\nОшибка: Для работы с raw-сокетами запустите терминал от имени АДМИНИСТРАТОРА.")
    except OSError as e:
        print(f"Ошибка сокета: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Python Traceroute Clone")
    parser.add_argument("target", help="IP или доменное имя")
    parser.add_argument("-n", "--resolve", action="store_true", help="Включить DNS разрешение имен")
    
    args = parser.parse_args()
    run_traceroute(args.target, resolve_names=args.resolve)