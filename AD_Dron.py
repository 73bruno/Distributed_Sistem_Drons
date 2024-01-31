import os
import socket
import sys
import json
import threading
import requests
import random
from time import sleep
import time
import base64
from prod_cons.consumer_Dron import main as mainCons
from prod_cons.producer_Dron import main as mainProd
#Api
# Establecer la ruta al archivo de certificado del sistema
#cert_path = "/Users/bruno/Desktop/SD/Prac/P2/cert.pem"

# Configurar la variable de entorno REQUESTS_CA_BUNDLE
#os.environ['REQUESTS_CA_BUNDLE'] = cert_path

#Encriptado de sockets
import secrets
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64


last_update_time = None

consumerDestino = None 
TopicDestino = "DESTINO"
POS_DESTINO = "0,0"
POS_ACTUAL = "0,0"

producerMovimientos = None
TopicMovimientos = "MOVIMIENTOS"

consumerMapa = None
TopicMapa = "MAPA"

##############################################
#                                            
#   ENCRYPT           
#         
##############################################
file_eng_public_key = "eng_public_key.pem"
file_dron_public_key = "dron_pub_key.pem"
file_dron_private_key = "dron_priv_key.pem"

def generate_key_pair():
    if os.path.exists(file_dron_private_key) and os.path.exists(file_dron_public_key):
        return
        
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    # Guardar la clave privada en el archivo
    with open(file_dron_private_key, "wb") as private_key_file:
        private_key_file.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    # Guardar la clave pública en el archivo
    with open(file_dron_public_key, "wb") as public_key_file:
        public_key_file.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )

def load_public_key(public_key_path):
    # Cargar la clave pública desde el archivo
    with open(public_key_path, "rb") as public_key_file:
        public_key = serialization.load_pem_public_key(
            public_key_file.read(),
            backend=default_backend()
        )
    return public_key

def encriptar_info(message, public_key_path):
    # Cargar la clave pública desde el archivo
    with open(public_key_path, "rb") as key_file:
        dron_public_key = serialization.load_pem_public_key(
            key_file.read(),
            backend=default_backend()
        )
    
    crypt_data = dron_public_key.encrypt( message.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return crypt_data

def desencriptar_info(crypt_data, private_key_path):
    # Cargar la clave privada desde el archivo
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )

    # Descifrar el mensaje utilizando la clave privada
    decrypted_message = private_key.decrypt(
        crypt_data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    return decrypted_message.decode('utf-8')

def decrypt_large_message(encrypted_symmetric_key, ciphertext, private_key_path):
    # Descifrar la clave simétrica con RSA
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )

    symmetric_key = private_key.decrypt(
        encrypted_symmetric_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    # Descifrar el mensaje con la clave simétrica
    cipher = Cipher(algorithms.AES(symmetric_key), modes.CFB(b'\0' * 16), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_message = decryptor.update(ciphertext) + decryptor.finalize()

    return decrypted_message

"""def print_key_file(file_path):
    with open(file_path, "rb") as key_file:
        key_data = key_file.read()
        print(f"Contenido de la clave en {file_path}:\n{key_data.decode('utf-8')}")"""


##############################################
#                                            
#   DRON
#         
##############################################

def create_dron_file(dron_id, password):
    file_name = f"dron_{dron_id}.txt"
    with open(file_name, "w") as file:
        file.write(f"ID: {dron_id}\nPassword: {password}")
    print(f"Archivo {file_name} creado con éxito.")


def run_dron_with_file(dron_id, engine_ip, engine_port,brocker_ip, brocker_port,registry_ip,registry_port):
    global consumerDestino,producerMovimientos,consumerMapa,POS_ACTUAL
    registry_url = f"https://{registry_ip}:{registry_port}/auth"

    # Lee el archivo del dron y extrae el token
    if dron_id != None:
        file_name = f"dron_{dron_id}.txt"
        try:
            with open(file_name, "r") as file:
                lines = file.readlines()
                for line in lines:
                    if line.startswith("Password: "):
                        password = line[len("Password: "):].strip()
                        break
        except FileNotFoundError:
            print(f"No se encontró el archivo para el dron (no esta registrado o el Id {dron_id} es incorrecto)")
            return
    else:
        password = f"password{random.randint(1, 1000000)}"

    # Construir los datos del dron para la solicitud al registro
    data_to_send = {
        "drone_id": dron_id,
        "password": password #Esto obviamente no es seguro pero se dejará asi ya que no es lo relevante en esta práctica
    }

    try:
        response = requests.post(registry_url, json=data_to_send, verify=False)  # El parámetro `verify=False` deshabilita la verificación del certificado SSL (Solo para desarrollo)
        response_data = response.json()

        if response.status_code == 200:
            if "Dron validado" in response_data["message"]:
                token = response_data["token"]
                time = response_data["timestamp"]
            elif "Nuevo dron registrado" in response_data["message"]:
                token = response_data["token"]
                time = response_data["timestamp"]
                dron_id = response_data["id"]
                create_dron_file(dron_id,password)
            elif "Contraseña incorrecta" in response_data["message"]:
                print("Contraseña incorrecta. Vuelva a intentarlo")
                sys.exit()
            elif "ID no existente en la BD" in response_data["message"]:
                print("El Dron con el que intentas iniciar sesión no está registrado.")
                sys.exit()
            else:
                print(f"Error al intentar registrarse/iniciar sesión con AD_Registry: {response_data}")
                sys.exit()

    except Exception as e:
        print(f"Error al conectar con el registro: {str(e)}")
        sys.exit()

    ##CONEXION CON ENGINE
    try:
        # Concatenar el ID y el token en una sola cadena
        data_to_send = f"{dron_id} {token}"
        # Conéctate al engine y envía el ID y el token para la autenticación
        engine_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        engine_client.connect((engine_ip, int(engine_port)))
        engine_client.send(data_to_send.encode('utf-8'))
        response = engine_client.recv(1024).decode('utf-8')

        if response != "Autenticado":
            if response.startswith("Autenticado "):
                last_position_str = response[len("Autenticado "):]
                POS_ACTUAL = last_position_str
                print(f"Reconexión exitosa para el dron {dron_id}.")
            else:
                print(f"Reconexión fallida para el dron {dron_id} en el engine.")
                engine_client.close()
                sys.exit()

        elif response == "Autenticado":
            print(f"Autenticación exitosa para el dron {dron_id}.")

        else:
            print(f"Autenticación fallida para el dron {dron_id} en el engine.")
            engine_client.close()
            sys.exit()

        # Recibir clave pública del servidor
        serialized_public_key = engine_client.recv(4096)
        eng_public_key = serialization.load_pem_public_key(
            serialized_public_key,
            backend=default_backend()
        )

        # Guarda la clave publica en el archivo
        with open(file_eng_public_key, "wb") as key_file:
            key_file.write(
                eng_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )

        #Envia clave publica a Engine
        generate_key_pair()
        public_key = load_public_key(file_dron_public_key)
        serialized_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        engine_client.sendall(serialized_public_key)

        engine_client.close() 


        consumerDestino = mainCons([brocker_ip,brocker_port, TopicDestino]) #Levantamos el consumer(asginamos el ID como grupo)
        producerMovimientos = mainProd([brocker_ip,brocker_port]) #Levantamos el producer
        sleep(0.3)
        consumerMapa = mainCons([brocker_ip,brocker_port,TopicMapa])
        hilo_actualiza_mapa = threading.Thread(target=actualizaMapa)
        hilo_actualiza_mapa.start()

        mostrar_mensaje_de_carga(0.01)
        sleep(3)
        engine_check_thread = threading.Thread(target=check_engine_offline)
        engine_check_thread.start()
        movimientos()
        print("Espectáculo Finalizado APAGUE SU DRON")
    except Exception as e:
        print(f"Error al conectar con el Engine: {str(e)}")
        sys.exit()
                                                   
def movimientos():
    figura = None
    movimientos = None
    espectaculoDetenido = False
    sleep(1)


    global POS_DESTINO,last_update_time
    figura = None

    for message in consumerDestino:
        cryp_message = base64.b64decode(message.value)
        message = desencriptar_info(cryp_message, file_dron_private_key)

        last_update_time = time.time()
        figuraExcep = json.loads(message)

        if figuraExcep["Nombre"] != "DETENER_ESPECTACULO" and figuraExcep["Nombre"] != "REANUDAR_ESPECTACULO" and espectaculoDetenido == False: 
            if figura == None or message != figura: #si entra una nueva figura, se comenzará a hacer 
                figura = message
                POS_DESTINO = obtener_destino_dron(figura,dron_id)
                movimientos = calcular_coordenadas_intermedias(POS_ACTUAL,POS_DESTINO)

        elif figuraExcep["Nombre"] == "DETENER_ESPECTACULO":
            espectaculoDetenido = True
            print("DRON VOlVIENDO A INICIO POR LAS TEMPERATURAS")
            POS_DESTINO = obtener_destino_dron(message,dron_id)
            movimientos = calcular_coordenadas_intermedias(POS_ACTUAL,POS_DESTINO)

        else:
            if figuraExcep["Nombre"] == "REANUDAR_ESPECTACULO":
                espectaculoDetenido = False
                print("DRON REANUDANDO ESPECTACULO. TEMPERATURA APTA")
                POS_DESTINO = obtener_destino_dron(figura,dron_id)
                movimientos = calcular_coordenadas_intermedias(POS_ACTUAL,POS_DESTINO)
                sleep(1)         

        avanzar_en_mapa(movimientos,dron_id)
    
def check_engine_offline():
    global last_update_time
    while True:
        current_time = time.time()
        if last_update_time is not None and current_time - last_update_time > 10:
            print("CONEXIÓN CON ENGINE PERDIDA. ESPERANDO RECONEXIÓN")
        # Espera durante un período de tiempo antes de volver a verificar la conexión
        time.sleep(5)

def actualizaMapa():
    for message in consumerMapa:
        ciphertext, encrypted_symmetric_key = message.value.split(" ")

        encrypted_symmetric_key = base64.b64decode(encrypted_symmetric_key)
        ciphertext = base64.b64decode(ciphertext)

        message = decrypt_large_message(encrypted_symmetric_key, ciphertext, file_dron_private_key)
        #cryp_message = base64.b64decode(message.value)
        #message = desencriptar_info(cryp_message, file_dron_private_key)
        mapa = json.loads(message.decode('utf-8'))
        mostrar_mapa(mapa)

def obtener_destino_dron(figura_json, dron_id):
    try:
        figura = json.loads(figura_json)
        if "Drones" in figura:
            for dron in figura["Drones"]:
                if int(dron["ID"]) == int(dron_id):
                    return dron["POS"]
    except json.JSONDecodeError:
        print("Error al decodificar la figura JSON. El formato JSON es incorrecto.")
    return "0,0"

def calcular_coordenadas_intermedias(posicion_actual, posicion_destino):
    x_actual, y_actual = map(int, posicion_actual.split(','))
    x_destino, y_destino = map(int, posicion_destino.split(','))

    coordenadas_intermedias = []

    # Agrega la primera coordenada
    coordenadas_intermedias.append(f"{x_actual},{y_actual}")

    while x_actual != x_destino:
        if x_actual < x_destino:
            x_actual += 1
        else:
            x_actual -= 1
        coordenadas_intermedias.append(f"{x_actual},{y_actual}")

    while y_actual != y_destino:
        if y_actual < y_destino:
            y_actual += 1
        else:
            y_actual -= 1
        coordenadas_intermedias.append(f"{x_actual},{y_actual}")

    return coordenadas_intermedias

def avanzar_en_mapa(movimientos,dron_id):
    global POS_ACTUAL

    if not movimientos :
        color = "verde"
        datos = {
        "casilla": POS_ACTUAL,
        "contenido": dron_id,
        "color": color
        }
    else:
        next_position = movimientos.pop(0)
        datos = {
        "casilla": next_position,
        "contenido": dron_id,
        "color": "rojo"
        }
        POS_ACTUAL = next_position
    
    mensaje_json = json.dumps(datos,sort_keys=True)
    cryp_message = encriptar_info(mensaje_json, file_eng_public_key)
    message = base64.b64encode(cryp_message).decode('utf-8')
    producerMovimientos.send(TopicMovimientos, value=message)
    sleep(1)
        
def mostrar_mapa(mapa):
    colores = {
        "blanco": "\x1b[0m",  # Restablece el color a su valor predeterminado
        "verde": "\x1b[32m",  # Verde
        "rojo": "\x1b[31m"   # Rojo
    }

    print("    ", end=" ")  # Espacio para los números de columna
    for col in range(20):
        print(f"{col:2}", end=" ")
    print()  # Nueva línea después de los números de columna

    for fila in range(20):
        print(f"{fila:2} |", end=" ")  # Número de fila
        for columna in range(20):
            coordenada = f"{fila},{columna}"  # Convierte las coordenadas a una cadena
            casilla = mapa.get(coordenada, {})  # Usa get para manejar claves que podrían no existir
            contenido = " " if casilla.get("contenido") == "vacio" else casilla.get("contenido", " ")  # Espacio en blanco si no hay contenido
            color = casilla.get("color", "blanco")  # Valor predeterminado: blanco
            color_code = colores.get(color, "\x1b[0m")  # Obtiene el código de color correspondiente
            print(f"{color_code}{contenido}\x1b[0m", end=" ")
        print()  # Nueva línea para cada fila

def mostrar_mensaje_de_carga(espera):
    for i in range(100):
        time.sleep(espera)
        sys.stdout.write('\r')
        progreso = (i + 1) / 100
        barra_de_progreso = "[" + "=" * int(50 * progreso) + " " * (50 - int(50 * progreso)) + "]"
        mensaje = f"Inicializando : {barra_de_progreso} {int(100 * progreso)}%"
        sys.stdout.write(mensaje)
        sys.stdout.flush()

    # Borra la línea de la barra de progreso
    sys.stdout.write('\r' + ' ' * len(mensaje) + '\r')
    sys.stdout.flush()
    print("Dron listo para el espectáculo")
    
if __name__ == "__main__":
    if len(sys.argv) == 8:
        engine_ip = sys.argv[1]
        engine_port = sys.argv[2]
        brocker_ip = sys.argv[3]
        brocker_port = sys.argv[4]
        dron_id = None
        if sys.argv[5] != "0":
            dron_id = int(sys.argv[5])
        registry_ip = sys.argv[6]
        registry_port = sys.argv[7]

        run_dron_with_file(dron_id, engine_ip, engine_port, brocker_ip, brocker_port,registry_ip,registry_port)
    else:
        print("Usa: python dron.py <Engine IP> <Engine Port> <Brocker IP> <Brocker Port> <Dron ID> <Registry_ip> <registry_port>")
        sys.exit(1)


