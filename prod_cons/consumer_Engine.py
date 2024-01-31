import sys
import json
from kafka import KafkaConsumer
from json import loads


def main(argv):
    broker_ip = argv[0]
    broker_port = argv[1]
    topic_name = argv[2]

    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers=[f'{broker_ip}:{broker_port}'],
        auto_offset_reset='latest',
        enable_auto_commit=True,
        value_deserializer=lambda x: loads(x.decode('utf-8')))

    return consumer

    
if __name__ == "__main__":
    main(sys.argv)