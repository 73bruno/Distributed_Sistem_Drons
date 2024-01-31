import sys
from kafka import KafkaProducer
from json import dumps

def main(argv):
    broker_ip = argv[0]
    broker_port = argv[1]
    producer = KafkaProducer(bootstrap_servers=[f'{broker_ip}:{broker_port}'],
                            value_serializer=lambda x: 
                            dumps(x).encode('utf-8'))
    return producer


if __name__ == "__main__":
    main(sys.argv)