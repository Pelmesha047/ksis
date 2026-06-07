import socket
import threading
from urllib.parse import urlparse
import os

# Настройки прокси
PROXY_HOST = '127.0.0.2'
PROXY_PORT = 8080
BLACKLIST_FILE = 'blacklist.txt'

# Таблица расшифровки HTTP-кодов, передаваемых браузеру в ответе сервера
STATUS_CODES = {
    100: 'Продолжай (Continue)',
    101: 'Переключение протоколов (Switching Protocols)',
    200: 'Успешно (OK)',
    201: 'Создано (Created)',
    204: 'Нет содержимого (No Content)',
    301: 'Перемещено навсегда (Moved Permanently)',
    302: 'Временное перенаправление (Found)',
    304: 'Не изменено (Not Modified)',
    400: 'Неверный запрос (Bad Request)',
    401: 'Требуется авторизация (Unauthorized)',
    403: 'Доступ запрещён (Forbidden)',
    404: 'Не найдено (Not Found)',
    405: 'Метод не разрешён (Method Not Allowed)',
    408: 'Время ожидания истекло (Request Timeout)',
    429: 'Слишком много запросов (Too Many Requests)',
    500: 'Внутренняя ошибка сервера (Internal Server Error)',
    502: 'Плохой шлюз (Bad Gateway)',
    503: 'Сервис недоступен (Service Unavailable)',
    504: 'Шлюз не отвечает (Gateway Timeout)',
}

def decode_status_code(status_line):
    """Возвращает числовой код и расшифровку из строки вида «HTTP/1.1 404 Not Found»."""
    parts = status_line.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None, status_line
    code = int(parts[1])
    return code, STATUS_CODES.get(code, ' '.join(parts[2:]) if len(parts) > 2 else 'Неизвестный код')

def print_status_codes_table():
    """Выводит таблицу расшифровки кодов при запуске прокси."""
    print('[*] Таблица расшифровки HTTP-кодов:')
    print(f"{'Код':<6} {'Расшифровка'}")
    print('-' * 50)
    for code in sorted(STATUS_CODES):
        print(f"{code:<6} {STATUS_CODES[code]}")

def load_blacklist():
    """Загружает список заблокированных доменов из файла."""
    if not os.path.exists(BLACKLIST_FILE):
        return set() # если ничего нет возвращает пустое множество
    with open(BLACKLIST_FILE, 'r') as f: # открываем в режиме чтения
        return set(line.strip().lower() for line in f if line.strip()) #читаем построчно, убираем пробелы, переводим в нижний регистр

def handle_client(client_socket, client_address, blacklist):
    """Обрабатывает соединение с клиентом в отдельном потоке.""" #каждый новый запрос в отдельном потоке
    try:
        # Читаем запрос от браузера
        request_data = client_socket.recv(8192) #получаем данные
        if not request_data:
            return #если их нет завершаем работу

        # Ищем конец заголовка
        headers_end = request_data.find(b'\r\n\r\n')
        if headers_end == -1:
            return
            
        lines = request_data.split(b'\r\n') #разделяем запрос на строки и берем первую
        first_line = lines[0].decode('utf-8', errors='ignore')
        
        try: #строка должна быть формата GET http://example.com/ HTTP/1.1
            method, url, version = first_line.split()
        except ValueError:
            return # некорректный запрос - прерываемся

        # Разбираем URL, чтобы достать хост, порт и путь
        parsed_url = urlparse(url) #команда для разбития
        host = parsed_url.hostname
        port = parsed_url.port or 80
        
        # Формируем относительный путь
        path = parsed_url.path if parsed_url.path else "/" #если пустой то слэш добавляем
        if parsed_url.query:
            path += "?" + parsed_url.query

        # Проверка черного списка
        if host and host.lower() in blacklist:
            print(f"[BLOCKED] {url} 403 — {STATUS_CODES[403]}")
            send_blocked_response(client_socket, url)
            return

        # Перезаписываем первую строку запроса (заменяем полный URL на путь)
        new_first_line = f"{method} {path} {version}\r\n".encode('utf-8')
        # Собираем новый запрос: новая первая строка + остальные заголовки и тело
        modified_request = new_first_line + request_data[request_data.find(b'\r\n') + 2:]

        # Подключаемся к целевому серверу
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote_socket:
            remote_socket.connect((host, port))
            remote_socket.sendall(modified_request)

            # Получаем первый ответ для журналирования статус-кода
            response_data = remote_socket.recv(8192)
            if response_data:
                response_first_line = response_data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                status_code = " ".join(response_first_line.split()[1:])
                code, description = decode_status_code(response_first_line)
                
                # Журналируем запрос в консоли: URL, код и расшифровка
                if code is not None:
                    print(f"{url} {status_code} — {description}")
                else:
                    print(f"{url} {status_code}")
                
                client_socket.sendall(response_data) #чтобы клиент понял что сервер ответил

                # Запускаем цикл для потоковой передачи
                while True: #прерывается при возвращении пустой строки
                    data = remote_socket.recv(8192)
                    if not data:
                        break
                    client_socket.sendall(data)

    except Exception as e:
        # Игнорируем ошибки обрыва соединения
        pass
    finally:
        client_socket.close()

def send_blocked_response(client_socket, url):
    """Отправляет кастомную HTML-страницу при блокировке."""
    html = f"""<html>
    <head><title>403 Forbidden</title></head>
    <body>
        <h1>Доступ запрещен</h1>
        <p>Запрашиваемый ресурс <b>{url}</b> находится в черном списке прокси-сервера.</p>
    </body>
    </html>"""
    
    response = (
        "HTTP/1.1 403 Forbidden\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(html.encode('utf-8'))}\r\n"
        "Connection: close\r\n\r\n"
        f"{html}"
    )
    client_socket.sendall(response.encode('utf-8'))

def start_proxy():
    """Запускает прокси-сервер."""
    blacklist = load_blacklist()
    
    # Создаем слушающий сокет
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #айпи 4 и тсп
    # Позволяем использовать адрес сразу после завершения программы
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind((PROXY_HOST, PROXY_PORT))
    server_socket.listen(100)
    
    print(f"[*] Прокси-сервер запущен на {PROXY_HOST}:{PROXY_PORT}")
    print_status_codes_table()
    if blacklist:
        print(f"[*] Загружен черный список: {', '.join(blacklist)}")
        
    try: # бесконечный цикл ожидания клиентов
        while True: #ждем подключения
            client_socket, client_address = server_socket.accept()
            # Для каждого клиента создаем новый поток
            client_thread = threading.Thread(
                target=handle_client, 
                args=(client_socket, client_address, blacklist)
            )
            client_thread.daemon = True #поток завершается при выключении программы
            client_thread.start()
    except KeyboardInterrupt:
        print("\n[*] Остановка прокси-сервера.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_proxy()