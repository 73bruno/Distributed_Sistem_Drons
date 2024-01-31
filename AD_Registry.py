from distutils.log import debug
import hashlib
import random 
from flask import Flask, jsonify, request
from flask_sslify import SSLify 
app = Flask(__name__)
sslify = SSLify(app)

FORMAT = 'utf-8'
MAX_CONEXIONES = 100
ConexionesActuales = 0
registro_file = "DB_DRONS.txt"

@app.route('/auth', methods=['POST'])
def handle_client():
    global ConexionesActuales
    if ConexionesActuales <= MAX_CONEXIONES:
        ConexionesActuales += 1

        try:
            data = request.json
            if not ('drone_id' in data and 'password' in data):
                return jsonify({"message": "Error en el formato de conexión"})
                
            registro, tokentime = comprobar_registro(data)
            
            if registro:
                if tokentime == (None, None):
                    return jsonify({"message": "Contraseña incorrecta"})
                else:
                    return jsonify({"message": "Dron validado", "token": tokentime[0], "timestamp": tokentime[1]})
            else:
                if tokentime == (None, None):
                    return jsonify({"message": "ID no existente en la BD"})
                else:
                    return jsonify({"message": "Nuevo dron registrado", "token": tokentime[0], "timestamp": tokentime[1], "id": data.get("drone_id")})
        except Exception as e:
            return jsonify({"message": f"Error en la solicitud: {str(e)}"})
        finally:
            ConexionesActuales -= 1
    else:
        return jsonify({"message": "Pruebe más tarde. Máximas conexiones simultáneas alcanzadas."})

        
def cifrar_irreversible(password):
    # Utilizar la función hash SHA-256
    hasher = hashlib.sha256()

    # Convertir la contraseña a bytes antes de pasarla a la función hash
    password_bytes = password.encode('utf-8')

    # Actualizar el objeto hash con los bytes de la contraseña
    hasher.update(password_bytes)

    # Obtener el hash resultante en formato hexadecimal
    hashed_password = hasher.hexdigest()

    return hashed_password

def comprobar_existencia_id(id_a_comprobar):
    try:
        with open(registro_file, "r") as archivo:
            lineas = archivo.readlines()
            for linea in lineas:
                partes = linea.strip().split(',')
                if len(partes) == 4:
                    id_actual = int(partes[0])
                    contrasena_actual = partes[1]
                    if id_actual == id_a_comprobar:
                        return True, contrasena_actual
            return False, None
    except FileNotFoundError:
        print("BBDD no encontrada")
        return False, None

def obtener_ultimo_id():
    try:
        with open(registro_file, "r") as archivo:
            lineas = archivo.readlines()
            if lineas:
                ultimo_registro = lineas[-1].strip()
                partes = ultimo_registro.split(',')
                if len(partes) == 4:
                    ultimo_id = int(partes[0])
                    return ultimo_id
                else:
                    return -1
            else:
                # Si el archivo está vacío, se asume que es el primer dron
                return 0
    except FileNotFoundError:
        # Si el archivo no existe, se asume que es el primer dron
        return 0

def asignar_id():
    ultimo_id = obtener_ultimo_id()
    if ultimo_id == -1:
        return str(-1)

    nuevo_id = ultimo_id + 1
    return str(nuevo_id)

def generar_codigo_hash(client_id,client_port):
    # Crear un objeto hash (en este caso, usaremos SHA-256)
    hasher = hashlib.sha256()
    # Actualizar el objeto hash con los datos
    data = f"{client_id}:{client_port}".encode(FORMAT)
    hasher.update(data)
    # Obtener el código de autenticación hash
    codigo_hash = hasher.hexdigest()

    return codigo_hash

def comprobar_registro(data):
    import time
    ID = data.get("drone_id")
    password = data.get("password")
    time = time.time()
    if ID != None:
        ID = int(ID)
        existe, password_db = comprobar_existencia_id(ID)
        if existe: #Dron ya registrado
            if cifrar_irreversible(password) == password_db:#Id registrado y contraseña correcta
                token = generar_codigo_hash(random.randint(1, 1000000), random.randint(1, 1000000))
                tokentime = (token, time)
                print(f"Asignado nuevo Token al cliente con ID {ID}")
                #Actualizar token de Dron en la BBDD
                actualizar_token(ID, cifrar_irreversible(password), token, time)
                return (True , tokentime)
            else:#Id registrado pero contraseña incorrecta
                return (True, (None,None))
        else: #ID no nulo y no registrado
            return(False, (None,None))
    else:#ID nulo (Solicitud de regsitro)
        # Asignar un ID y un Token al cliente
        client_id = asignar_id()
        if client_id == "-1":
            print(f"El archivo {registro_file} está mal formateado. Cerrando conexión")
            error_message = "Error_Registry_File"
        token = generar_codigo_hash(random.randint(1, 1000000),random.randint(1, 1000000))
        print(f"Asignado ID {client_id} y token al cliente")
        
        #Guardar Dron en la BBDD
        with open(registro_file, "a") as file:
            file.write(f"{client_id},{cifrar_irreversible(password)},{token},{time}\n")

        data["drone_id"] = client_id  # Modificar el ID en el diccionario original
        return (False, (token,time))


def actualizar_token(dron_id, password, new_token, current_time):
     # Leemos todas las líneas del archivo de registro
    with open(registro_file, "r") as file:
        lines = file.readlines()

    # Buscamos la línea correspondiente al drone_id
    for i, line in enumerate(lines):
        data = line.strip().split(',')
        existing_drone_id = int(data[0])
        if existing_drone_id == dron_id:
            # Actualizamos la información en la línea
            lines[i] = f"{dron_id},{password},{new_token},{current_time}\n"
            break

    # Escribimos las líneas actualizadas de vuelta al archivo
    with open(registro_file, "w") as file:
        file.writelines(lines)

######################### MAIN ##########################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, ssl_context=('cert.pem', 'key.pem'))
    print(f"API INICIALIZADA ")
