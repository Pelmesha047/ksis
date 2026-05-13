import os
import shutil # Для высокоуровневых операций с файлами (копирование, удаление папок с содержимым)
import email.utils # Для правильного форматирования даты по стандартам интернета
from flask import Flask, request, jsonify, send_file, Response, abort
# request - объект, который содержит все данные, пришедшие от пользователя (заголовки, тело запроса)
# jsonify - функция для удобного превращения словарей Python в JSON-ответы
# send_file - функция для отправки самого файла пользователю
# Response - класс для создания нестандартных ответов (например, когда нужны только заголовки)
# abort - функция для экстренного прерывания запроса с ошибкой
# Создаем экземпляр приложения Flask
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False

# Папка, где будут физически храниться файлы
STORAGE_DIR = os.path.abspath('storage_data') # abspath делает путь абсолютным

# Убедимся, что папка хранилища существует при запуске
os.makedirs(STORAGE_DIR, exist_ok=True)

def get_secure_path(filepath):
    """
    Вспомогательная функция. 
    Преобразует URL-путь в физический путь на диске и защищает от выхода за пределы хранилища.
    """
    # Собираем полный путь - базовая папка+запрос
    abs_path = os.path.abspath(os.path.join(STORAGE_DIR, filepath))
    
    # Если итоговый путь не начинается с базовой папки - это попытка взлома
    if not abs_path.startswith(STORAGE_DIR):
        abort(403, description="Доступ запрещен") # 403 Forbidden
        
    return abs_path

# Декораторы @app.route говорят Flask, какие URL-адреса должна обрабатывать следующая функция.
# Первый обрабатывает 'http://localhost:5000/' (корень).
# Второй перехватывает все пути после слеша, '/folder/file.txt', и сохраняет их в переменную filepath.
# Маршрут '/' нужен для работы с корневым каталогом, а '/<path:filepath>' для всех остальных файлов и папок
@app.route('/', defaults={'filepath': ''}, methods=['GET', 'PUT', 'HEAD', 'DELETE'])
@app.route('/<path:filepath>', methods=['GET', 'PUT', 'HEAD', 'DELETE'])
def storage(filepath):
    # Получаем безопасный физический путь на диске
    target_path = get_secure_path(filepath)

    if request.method == 'PUT': #загрузка или копирование
        # Проверяем, есть ли заголовок для копирования
        copy_from = request.headers.get('X-Copy-From')
        print(f"--- Пытаюсь создать файл по пути: {target_path}")
        print(f"--- Заголовок копирования: {copy_from}")

        # os.path.dirname берет путь к файлу и возвращает только путь к папке, в которой он лежит.
        # Создаем все родительские папки, если их еще нет
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if copy_from: 
            # Убираем в начале слеш, чтобы путь корректно приклеился к хранилищу
            source_filename = copy_from.strip().lstrip('/')
            source_path = get_secure_path(source_filename)
            
            print(f"--- РЕАЛЬНЫЙ ПУТЬ ИСТОЧНИКА: {source_path}")
            
            if not os.path.exists(source_path) or not os.path.isfile(source_path):
                return jsonify({"error": "Исходный файл не найден"}), 404 # 404 Not Found
            
            # Функция copy2 копирует файл вместе с его метаданными (датой создания и т.д.)
            shutil.copy2(source_path, target_path)
            return jsonify({"message": f"Файл скопирован из {copy_from}"}), 201 # 201 Created
        else:
            # Записываем сырые данные из тела запроса (request.data) в файл
            with open(target_path, 'wb') as f:
                f.write(request.data)
            return jsonify({"message": "Файл успешно загружен"}), 201 # 201 Created

    elif request.method == 'GET':
        if not os.path.exists(target_path):
            return jsonify({"error": "Файл или папка не найдены"}), 404

        if os.path.isdir(target_path):
            # Если это папка - возвращаем список файлов в формате JSON
            files = os.listdir(target_path)
            return jsonify({"directory": filepath, "contents": files}), 200 # 200 OK
        else:
            # Если это файл - отправляем сам файл
            return send_file(
                target_path, 
                as_attachment=True, 
                download_name=os.path.basename(target_path)
            )

    elif request.method == 'HEAD':
        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            # Для HEAD мы не возвращаем тело (JSON), только статус и заголовки
            # проверяем только файлы
            return Response(status=404)
        
        # Получаем размер и дату изменения
        size = os.path.getsize(target_path)
        mtime = os.path.getmtime(target_path)
        
        # Форматируем дату по стандарту
        mtime_st = email.utils.formatdate(mtime, usegmt=True)
        #собираем словарь
        headers = {
            'Content-Length': str(size),
            'Last-Modified': mtime_st
        }
        return Response(headers=headers, status=200)

    elif request.method == 'DELETE':
        if not os.path.exists(target_path):
            return jsonify({"error": "Файл или папка не найдены"}), 404
            
        if os.path.isdir(target_path):
            # Удаляем папку со всем содержимым
            shutil.rmtree(target_path)
        else:
            # Удаляем один файл
            os.remove(target_path)
            
        return jsonify({"message": "Успешно удалено"}), 200


if __name__ == '__main__':
    # Запускаем сервер на порту 5000
    app.run(host='0.0.0.0', port=5000, debug=True)