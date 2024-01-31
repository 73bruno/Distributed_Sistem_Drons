from asyncio import FastChildWatcher
from datetime import datetime
from email import message
import socket
import threading
import time
import sys
import os
import json
from time import sleep
import requests
import base64

from prod_cons.producer_Engine import main as mainProd
from prod_cons.consumer_Engine import main as mainCons

#Encriptado de sockets
import secrets
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64

reconexion = False 
# Obtiene los argumentos de la línea de comandos
if len(sys.argv) == 7 :
    listen_port = int(sys.argv[1])
    max_drones = int(sys.argv[2])
    broker_ip = sys.argv[3]
    broker_port = int(sys.argv[4])
    weather_ip = sys.argv[5]
    weather_port = int(sys.argv[6])
elif len(sys.argv) == 8:
    listen_port = int(sys.argv[1])
    max_drones = int(sys.argv[2])
    broker_ip = sys.argv[3]
    broker_port = int(sys.argv[4])
    weather_ip = sys.argv[5]
    weather_port = int(sys.argv[6])
    if sys.argv[7] == "-r":
        reconexion = True
else:
    print("Uso: python AD_Engine.py <Puerto de escucha> <Máximo de drones> <IP del Broker> <Puerto del Broker> <IP del AD_Weather> <Puerto del AD_Weather> '-r'")
    sys.exit()

# Variables globales
host_ip = socket.gethostbyname(socket.gethostname())
FORMAT = 'utf-8'
HEADER = 64
drones = {}
mapa = {} #Diccionario que representa un mapa 
      
for fila in range(20):
    for columna in range(20):
        coordenada = f"{fila},{columna}" #cadena para poder enviarlo por kafka
        mapa[coordenada] = {"color": "blanco", "contenido": "vacio"}

registro_file = "DB_DRONS.txt"
FIG_FILE = "AwD_figuras.json"
producerDestino = None
TopicDestino = "DESTINO"

producerMapa = None
TopicMapa = "MAPA"

consumerMovimientos = None
TopicMovimientos = "MOVIMIENTOS"

espectaculoDetenido = False


##############################################
#                                            
#   FRONT          
#         
##############################################
"""def enviar_datos_al_servidor():
    global drones,mapa
    while True:
        # Obtén los datos que deseas enviar (mapa y drones)
        datos_a_enviar = {
            'mapa': mapa,
            'drones': drones,
        }

        # Realiza la solicitud POST al servidor Node.js
        url_actualizar_datos = 'https://localhost:4000'  # Ajusta la URL según tu configuración
        try:
            respuesta = requests.post(url_actualizar_datos, json=datos_a_enviar, verify=False)
            if respuesta.status_code == 200:
                print("Datos enviados correctamente al servidor.")
            else:
                print(f"Error al enviar datos. Código de estado: {respuesta.status_code}")
        except requests.RequestException as e:
            print(f"Error en la solicitud: {e}")

        # Espera antes de enviar datos nuevamente (ajusta según tus necesidades)
        time.sleep(1)"""
##############################################
#                                            
#   AUDITORIA          
#         
##############################################
eventos = ["Registro","Autentificación","Conexión","Envio","Recepción","Deconexión","Detención_ejecución","Error","Actualizar_Var"]

def registrar_evento(host_ip,current_time,i,desc):
    log_entry = {
    "timestamp": current_time,
    "ip": host_ip,
    "action": eventos[i],
    "description": desc
    }

    with open("auditoria.log", "a") as log_file:
        log_file.write(str(log_entry) + "\n")


##############################################
#                                            
#   CIFRADO                  
#         
##############################################

file_eng_public_key = "eng_pub_key.pem"
file_eng_private_key = "eng_priv_key.pem"
file_dron_public_key = "dron_public_key.pem"

def generate_key_pair():
    if os.path.exists(file_eng_private_key) and os.path.exists(file_eng_public_key):
        return

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    # Guardar la clave privada en el archivo
    with open(file_eng_private_key, "wb") as private_key_file:
        private_key_file.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    # Guardar la clave pública en el archivo
    with open(file_eng_public_key, "wb") as public_key_file:
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
        eng_public_key = serialization.load_pem_public_key(
            key_file.read(),
            backend=default_backend()
        )
    #print(sys.getsizeof(message))
    crypt_data = eng_public_key.encrypt(
        message.encode('utf-8'),
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

"""def print_key_file(file_path):
    with open(file_path, "rb") as key_file:
        key_data = key_file.read()
        print(f"Contenido de la clave en {file_path}:\n{key_data.decode('utf-8')}")"""


def encrypt_large_message(message, public_key):
    # Generar una clave aleatoria para cifrado simétrico
    symmetric_key = secrets.token_bytes(32)  # 256 bits

    # Cifrar el mensaje con la clave simétrica
    cipher = Cipher(algorithms.AES(symmetric_key), modes.CFB(b'\0' * 16), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(message) + encryptor.finalize()

    # Cifrar la clave simétrica con RSA
    encrypted_symmetric_key = public_key.encrypt(
        symmetric_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    return encrypted_symmetric_key, ciphertext


##############################################
#                                            
#   DRONES                    
#         
##############################################

def handle_drone():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', listen_port))
    server.listen(5)
    
    print(f"AD Engine listening on port {listen_port}")
    connected_drones = len(drones)
    while True:
        conn, addr = server.accept()

        if connected_drones < max_drones:
            dron_ip, _ = addr
            registrar_evento(dron_ip, datetime.now(),2,"Intento de conexión de Dron a Engine")
            # Recibir la cadena del servidor
            data = conn.recv(4096)
            received_data = data.decode('utf-8')
            registrar_evento(dron_ip, datetime.now(),4,f"Recepción de datos de Dron: {received_data}")
            
            # Dividir la cadena en ID y token utilizando el carácter especial (espacio en este caso)
            dron_id, token = received_data.split(" ")
            if autenticar_dron(dron_id, token, registro_file):
                registrar_evento(dron_ip, datetime.now(),1,"Autentificación exitosa de Dron")
                # Envía un mensaje de autenticación al dron
                if dron_id not in drones:
                    message = "Autenticado"
                    conn.send(message.encode('utf-8'))
                    print(f"Drone {dron_id} conectado.")
                    registrar_evento(dron_ip, datetime.now(),2,"Conexión exitosa de Dron")
                    # Almacena el dron y su tiempo de último input  
                    drones[dron_id] = {
                        "last_update_time": None,
                        "position": (0,0),
                        "estado": "Activo",
                        "color": "rojo"
                    }
                else:
                    print(f"Drone {dron_id} reconectado.")
                    registrar_evento(dron_ip, datetime.now(),2,"Reconexión exitosa de Dron")
                    last_position = drones[dron_id].get("position", (0,0))  # Obtén la última posición o (0, 0) si no existe
                    drones[dron_id] = {
                        "last_update_time": None,
                        "position": last_position,
                        "estado": "Activo",
                        "color": "rojo"
                    }
  
                    last_position_str = f"{last_position[0]},{last_position[1]}"  # Convierte la tupla a una cadena
                    message_to_send = "Autenticado " + last_position_str
                    conn.send(message_to_send.encode('utf-8'))
                
            else:
                # Autenticación fallida, cierra la conexión
                registrar_evento(dron_ip, datetime.now(),1,"Autentificación fallida de Dron")
                print(f"Authentication failed for drone {dron_id}. Closing the connection.")
                conn.close()     
        else:
            registrar_evento(dron_ip, datetime.now(),1,"Autentificación fallida de Dron (N. máximo de drones alcanzado)")
            print("Max drones reached. Rejecting connection.") 
            conn.close()
        
        generate_key_pair()
        #Envia clave publica a Dron
        public_key = load_public_key(file_eng_public_key)
        serialized_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        conn.sendall(serialized_public_key)
        registrar_evento(host_ip, datetime.now(),3,f"Envio de clave publica a Dron {dron_ip}")

        # Recibir clave pública del dron
        serialized_public_key = conn.recv(4096)
        registrar_evento(dron_ip, datetime.now(),4,"Recepción de clave publica por Engine")
        dron_public_key = serialization.load_pem_public_key(
            serialized_public_key,
            backend=default_backend()
        )
        #print(f"serialized_public_key {serialized_public_key.decode('utf-8')}")
        # Guarda la clave publica en el archivo
        with open(file_dron_public_key, "wb") as key_file:
            key_file.write(
                dron_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )

def autenticar_dron(dron_id, token, registro_file):
    actual_time = time.time()

    with open(registro_file, "r") as file:
        registros = file.readlines()
        for registro in registros:
            elements = registro.strip().split(",")
            if len(elements) >= 4:  # Asegurémonos de que haya al menos 4 elementos en el registro
                dron_id_registrado = elements[0]
                dron_token = elements[2]
                token_creation_time = float(elements[3])

                # Verificar si el token pertenece al dron y si el tiempo actual es menor que el tiempo de creación del token
                if dron_id_registrado == dron_id and dron_token == token and (actual_time - token_creation_time <= 20):
                    return True

    return False  # No se encontró una coincidencia

def check_dron_status():
    global drones
    while True:
        current_time = time.time()

        for drone_id, drone_data in drones.items():
            last_update_time = drone_data["last_update_time"]
            if last_update_time is not None and current_time - last_update_time > 3:
                drones[drone_id]["estado"] = "No Activo"  # Actualiza el estado en el diccionario de drones
                registrar_evento(host_ip, datetime.now(),5,f"Dron {drone_id} desconectado")
                #actualizar_datos()
            else:
                drones[drone_id]["estado"] = "Activo"  # Actualiza el estado en el diccionario de drones
        sleep(0.1)

##############################################
#                                            
#   WEATHER             
#         
##############################################

figura_detener_espectaculo = {
        "Nombre": "DETENER_ESPECTACULO",
        "Drones": [
            {"ID": 1, "POS": "0,0"},
            {"ID": 2, "POS": "0,0"},
            {"ID": 3, "POS": "0,0"},
            {"ID": 4, "POS": "0,0"},
            {"ID": 5, "POS": "0,0"},
            {"ID": 6, "POS": "0,0"},
            {"ID": 7, "POS": "0,0"},
            {"ID": 8, "POS": "0,0"},
            {"ID": 9, "POS": "0,0"},
            {"ID": 10, "POS": "0,0"},
            {"ID": 11, "POS": "0,0"},
            {"ID": 12, "POS": "0,0"},
            {"ID": 13, "POS": "0,0"},
            {"ID": 14, "POS": "0,0"},
            {"ID": 15, "POS": "0,0"}
        ]
    }

figura_reanudar_espectaculo = {
        "Nombre": "REANUDAR_ESPECTACULO",
        "Drones": [
            {"ID": 1, "POS": "0,0"},
            {"ID": 2, "POS": "0,0"},
            {"ID": 3, "POS": "0,0"},
            {"ID": 4, "POS": "0,0"},
            {"ID": 5, "POS": "0,0"},
            {"ID": 6, "POS": "0,0"},
            {"ID": 7, "POS": "0,0"},
            {"ID": 8, "POS": "0,0"},
            {"ID": 9, "POS": "0,0"},
            {"ID": 10, "POS": "0,0"},
            {"ID": 11, "POS": "0,0"},
            {"ID": 12, "POS": "0,0"},
            {"ID": 13, "POS": "0,0"},
            {"ID": 14, "POS": "0,0"},
            {"ID": 15, "POS": "0,0"}
        ]
    }

def consume_api_OW():
    try:
        ow_api_key = "960611bd23d01eed974c5b63ed6f3717"

        global espectaculoDetenido
        figura_json = None
        while True:
            try:
                with open('ciudad.txt', 'r') as file:
                    ciudad = file.readline().strip()  # Elimina cualquier espacio en blanco alrededor
                url = f"https://api.openweathermap.org/data/2.5/weather?q={ciudad}&appid={ow_api_key}"
                # Realizar la solicitud HTTP
                response = requests.get(url)
                response.raise_for_status()  # Verificar si hay errores en la respuesta HTTP
                registrar_evento(host_ip, datetime.now(),4,f"Temperatura consultada en OpenWeather")
                # Extraer la temperatura de la respuesta JSON
                data = response.json()
                temperatura_kelvin = data['main']['temp']
                temperatura = temperatura_kelvin - 273.15
                

                if not espectaculoDetenido:
                    if (temperatura < -5 or temperatura > 45) and not espectaculoDetenido:
                        print(f"Temperatura Límite Excedida. Hay {temperatura} grados.")
                        registrar_evento(host_ip, datetime.now(),6,f"Espectaculo detenido por temperatura: {temperatura}")
                        figura_json = json.dumps(figura_detener_espectaculo,sort_keys=True)
                        cryp_message = encriptar_info(figura_json, file_dron_public_key)
                        message = base64.b64encode(cryp_message).decode('utf-8')
                        producerDestino.send(TopicDestino, value = message)
                        print("DETENIENDO ESPECTACULO")
                        espectaculoDetenido = True

                else:
                    if not temperatura < -5 or temperatura > 45:
                        print("REANUDANDO ESPECTACULO. TEMPERATURA APTA")
                        registrar_evento(host_ip, datetime.now(),6,f"Espectaculo reanudado, temperatura apta: {temperatura}")
                        figura_json = json.dumps(figura_reanudar_espectaculo,sort_keys=True)
                        cryp_message = encriptar_info(figura_json, file_dron_public_key)
                        message = base64.b64encode(cryp_message).decode('utf-8')
                        producerDestino.send(TopicDestino, value = message)
                        espectaculoDetenido = False

            except requests.exceptions.RequestException as e:
                # Manejar errores de solicitud HTTP
                print(f"Error en la solicitud HTTP a OpenWeather: {e}")
                registrar_evento(host_ip, datetime.now(),7,f"Error en la solicitud HTTP a OpenWeather: {e}")
            
            except KeyError as e:
                # Manejar errores si la estructura de la respuesta JSON no es como se esperaba
                print(f"Error al extraer la temperatura de la respuesta JSON: {e}")
                registrar_evento(host_ip, datetime.now(),7,f"Error al extraer la temperatura de la respuesta JSON: {e}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("La ejecución fue interrumpida por el usuario.")  
        registrar_evento(host_ip, datetime.now(),7,"La ejecución fue interrumpida por el usuario")
        

##############################################
#                                            
#   MAPA             
#         
##############################################

def recibir_actualizacion(): #consumerMovimientos
    global consumerMovimientos
    for message in consumerMovimientos:
        cryp_message = base64.b64decode(message.value)
        message = desencriptar_info(cryp_message, file_eng_private_key)
        registrar_evento(host_ip, datetime.now(),4,f"Movimiento de Dron recibido en Engine: {message}")
        return message

def enviar_mapa(mapa): #producerMapa
    global producerMapa
    registrar_evento(host_ip, datetime.now(),3,f"Mapa enviado por engine a Dron: {mapa}")
    mapa_json = json.dumps(mapa,sort_keys=True)
    mapa_json_bytes = mapa_json.encode('utf-8')
    encrypted_symmetric_key, ciphertext = encrypt_large_message(mapa_json_bytes, load_public_key(file_dron_public_key))
    #cryp_message = encriptar_info(mapa_json, file_dron_public_key)
    aes_cryp_message = base64.b64encode(ciphertext).decode('utf-8')
    aes_cryp_key = base64.b64encode(encrypted_symmetric_key).decode('utf-8')
    message = f"{aes_cryp_message} {aes_cryp_key}"
    producerMapa.send(TopicMapa, value=message)

def actualizaMapa():
    while True:
        # Esperar a recibir una actualización del Consumer de MOVIMIENTOS
        recibe_mov_dron = recibir_actualizacion()
        # Actualizar el mapa con la nueva información
        mapa = actualizar_mapa(recibe_mov_dron)
        # Enviar el mapa actualizado al Producer de MAPA
        enviar_mapa(mapa)

def actualizar_mapa(mensaje_json):
    global mapa,drones
    actualizacion = json.loads(mensaje_json)
    casilla_nueva = actualizacion["casilla"]
    dron = str(actualizacion["contenido"])
    color = actualizacion["color"]

    fila, columna = map(int, casilla_nueva.split(','))
    position = (fila, columna)

    fila_anterior, columna_anterior = drones[dron]["position"]
    casilla_anterior = f"{fila_anterior},{columna_anterior}"


    #actualizamos info del dron
    drones[dron] = {
        "last_update_time": time.time(),
        "position": position,
        "estado": "Activo",
        "color": color
        }
    
    # Buscamos si algún dron está no activo en la estructura de drones
    for drone_id, drone_data in drones.items():
        if drone_data["estado"] == "No Activo":
            # Restablecemos la posición del dron no activo en el mapa
            fila, columna = drone_data["position"]
            casilla_no_activo = f"{fila},{columna}"
            mapa[casilla_no_activo] = {"color": "blanco", "contenido": "vacio"}

    #print(f"{casilla_nueva},{dron},{color},{casilla_anterior}")
    if casilla_anterior != casilla_nueva and casilla_anterior != None:
        if casilla_anterior in mapa and mapa[casilla_anterior]["contenido"] == dron:
            mapa[casilla_anterior] = {"color": "blanco", "contenido": "vacio"}

    # Actualizamos el mapa con la nueva información
    mapa[casilla_nueva] = {"contenido": dron, "color": color}
    registrar_evento(host_ip, datetime.now(),8,"Actualizamos y mostramos mapa en Eng")
    #actualizar_datos()
    mostrar_mapa(mapa)
    return mapa

def mostrar_mapa(mapa):
    colores = {
        "blanco": "\x1b[0m",
        "verde": "\x1b[32m",
        "rojo": "\x1b[31m",
        "amarillo": "\x1b[33m"  
    }

    connected_drones = sum(1 for drone_data in drones.values() if drone_data.get("estado") == "Activo")

    print(f"DRONES ACTIVOS: {connected_drones}")
    print("ESTADO DE LOS DRONES:")
    for drone_id, drone_data in drones.items():
        estado = drone_data.get("estado")
        position = drone_data.get("position", "Desconocida")

        print(f"{drone_id} - {estado}", end="")

        if estado == "No Activo":
            print(f" - Última Posición: {position}", end=" ## ")
        else:
            print("", end=" ## ")


    print()


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

##############################################
#                                            
#   FIGURAS(Procesar y Enviar)                     
#         
##############################################
espectaculo = False

def espectaculoFinalizado(figura):
    global espectaculo, drones
    todos_verdes = False

    drones_en_espectaculo = [dron["ID"] for dron in figura["Drones"]]

    # Verifica si todos los drones en la estructura de drones han llegado al destino (estado "verde").
    todos_verdes = True

    for dron in drones_en_espectaculo: 
        dron = str(dron)
        if dron in drones:
            if drones[dron]["color"] != "verde":
                todos_verdes = False
                break
    al_menos_un_dron_en_mapa = any(casilla["contenido"] != "vacio" for casilla in mapa.values())

    if (al_menos_un_dron_en_mapa and todos_verdes):
        espectaculo = True

def cargar_datos_desde_json(FIG_FILE):
    try:
        with open(FIG_FILE, 'r') as archivo:
            datos = json.load(archivo)
            return datos
    except FileNotFoundError:
        print(f"El archivo {FIG_FILE} no se encontró.")
        return None
    except json.JSONDecodeError:
        print(f"Error al decodificar el archivo {FIG_FILE}. El formato JSON es incorrecto.")
        return None

def obtener_figuras(datos):
    if "figuras" in datos:
        return datos["figuras"]
    else:
        return None

def cargarFiguras():
    datos = cargar_datos_desde_json(FIG_FILE)
    figuras = obtener_figuras(datos)
    return figuras

def empiezaEspectaculo(figuras): #producerDestino
    global espectaculo
    espectaculo = False 
    for figura in figuras:
        recovery_data = {
            "mapa": mapa,
            "drones": drones,
            "figura": figura
        }
        guardar_datos_reconexion(recovery_data)
        figura_json = json.dumps(figura, sort_keys=True)
        while not espectaculo:
            cryp_message = encriptar_info(figura_json, file_dron_public_key)
            message = base64.b64encode(cryp_message).decode('utf-8')
            producerDestino.send(TopicDestino, value=message)
            sleep(2)
            espectaculoFinalizado(figura) #actualiza la variable espectaculo (True) cuando este haya acabado
        
        espectaculo = False 
        print("ESPECTACULO FINALIZADO")
        registrar_evento(host_ip, datetime.now(),6,"Espectaculo finalizado (todas las figuras han realizadas)")
        mostrar_mensaje_de_carga_espec(0.035)

##############################################
#                                            
#   MAIN                     
#         
##############################################
def cargar_datos_reconexion():
    nombre_archivo = "recovery.txt"
    try:
        with open(nombre_archivo, 'r') as archivo:
            recovery_data = json.load(archivo)

        return recovery_data

    except FileNotFoundError:
        print(f"El archivo {nombre_archivo} no existe.")
        sys.exit()
    except json.JSONDecodeError:
        print(f"Error al decodificar el archivo {nombre_archivo}. Verifica el formato JSON.")
        sys.exit()

def guardar_datos_reconexion(datos):
    nombre_archivo = "recovery.txt"
    with open(nombre_archivo, 'w') as archivo:
        json.dump(datos, archivo, indent=4)

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

def mostrar_mensaje_de_carga_espec(espera):
    for i in range(100):
        time.sleep(espera)
        sys.stdout.write('\r')
        progreso = (i + 1) / 100
        barra_de_progreso = "[" + "=" * int(50 * progreso) + " " * (50 - int(50 * progreso)) + "]"
        mensaje = f"BUSCANDO NUEVAS FIGURAS : {barra_de_progreso} {int(100 * progreso)}%"
        sys.stdout.write(mensaje)
        sys.stdout.flush()

    # Borra la línea de la barra de progreso
    sys.stdout.write('\r' + ' ' * len(mensaje) + '\r')
    sys.stdout.flush()
if __name__ == "__main__":
    if not reconexion:
        hiloSocketsDrons = threading.Thread(target=handle_drone)
        hiloSocketsDrons.start()


        figuras = cargarFiguras()
        producerDestino = mainProd([broker_ip,broker_port])  # Levantamos el producer de Destino
        producerMapa = mainProd([broker_ip,broker_port]) # Levantamos el producer de Mapa
        consumerMovimientos =  mainCons([broker_ip,broker_port,TopicMovimientos]) # Levantamos el consumer de movimientos

        sleep(0.5)
        mostrar_mensaje_de_carga(0.03)

        print("Presiona ENTER en cualquier momento para comenzar el espectáculo...")
        print("↓↓ESPERANDO DRONES↓↓")
        input()
        sleep(3)

        hiloEspectaculo = threading.Thread(target=empiezaEspectaculo, args=([figuras]))
        hiloEspectaculo.start()

        hilo_actualiza_mapa = threading.Thread(target=actualizaMapa)
        hilo_actualiza_mapa.start()

        sleep(1)#damos tiempo a que empiece el espectaculo
        hilo_drones_conectados = threading.Thread(target=check_dron_status)
        hilo_drones_conectados.start()

        hiloWeather = threading.Thread(target=consume_api_OW)
        hiloWeather.start()

        """hilofront = threading.Thread(target=enviar_datos_al_servidor)
        hilofront.start()"""
    else:
        print("RECONEXIÓN DE ENGINE \n")
        recovery_data = cargar_datos_reconexion()
        figura = recovery_data["figura"]
        drones = recovery_data["drones"]
        mapa = recovery_data["mapa"]

        hiloSocketsDrons = threading.Thread(target=handle_drone)
        hiloSocketsDrons.start()


        figuras = cargarFiguras()
        # Obtener el índice de la figura actual en la lista de figuras
        indice_figura_actual = -1
        for i, figura in enumerate(figuras):
            if figura["Nombre"] == figura.get("Nombre"):
                indice_figura_actual = i
                break
        # Eliminar las figuras anteriores a la figura actual
        figuras = figuras[indice_figura_actual:]
        producerDestino = mainProd([broker_ip,broker_port])  # Levantamos el producer de Destino
        producerMapa = mainProd([broker_ip,broker_port]) # Levantamos el producer de Mapa
        consumerMovimientos =  mainCons([broker_ip,broker_port,TopicMovimientos]) # Levantamos el consumer de movimientos
        mostrar_mensaje_de_carga(0.05)
        sleep(3)

        hiloEspectaculo = threading.Thread(target=empiezaEspectaculo, args=([figuras]))
        hiloEspectaculo.start()

        hilo_actualiza_mapa = threading.Thread(target=actualizaMapa)
        hilo_actualiza_mapa.start()

        sleep(1)#damos tiempo a que empiece el espectaculo
        hilo_drones_conectados = threading.Thread(target=check_dron_status)
        hilo_drones_conectados.start()

        hiloWeather = threading.Thread(target=consume_api_OW)
        hiloWeather.start()

        """hilofront = threading.Thread(target=enviar_datos_al_servidor)
        hilofront.start()"""