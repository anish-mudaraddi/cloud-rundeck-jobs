import json
import pika
from pika.credentials import PlainCredentials
from pika.exchange_type import ExchangeType
import eventlet

from st2reactor.sensor.base import Sensor

class RabbitSensor(Sensor):

    def __init__(self, sensor_service, config=None):
        super(RabbitSensor, self).__init__(sensor_service=sensor_service, config=config)

        self._logger = self._sensor_service.get_logger(name=self.__class__.__name__)

        self.host = self._config["rabbit_config"]["host"]
        self.port = self._config["rabbit_config"]["port"]
        self.queue = self._config["rabbit_config"]["queue"]
        self.username = self._config["rabbit_config"]["username"]
        self.password = self._config["rabbit_config"]["password"]
        self.exchange = self._config["rabbit_config"]["exchange"]
        self.exchange_type = self._config["rabbit_config"]["exchange_type"]
        self.exchange_durable = self._config["rabbit_config"]["exchange_durable"]
        self.routing_key = self._config["rabbit_config"]["routing_key"]

        self.conn = None
        self.channel = None

    def run(self):
        self._logger.info('Starting to consume messages from RabbitMQ %s', self.queue)
        # run in an eventlet in-order to yield correctly
        gt = eventlet.spawn(self.channel.start_consuming)
        # wait else the sensor will quit
        gt.wait()

    def cleanup(self):
        if self.conn:
            self.conn.close()
            
    def is_aq_message(message):
    """
    Check to see if the metadata in the message contains entries that suggest it
    is for an Aquilon VM.
    """
        logger.debug("Payload meta: %s" % message.get("payload").get("metadata"))

        metadata = message.get("payload").get("metadata")
        if metadata:
            if set(metadata.keys()).intersection(['AQ_DOMAIN', 'AQ_SANDBOX', 'AQ_OSVERSION', 'AQ_PERSONALITY', 'AQ_ARCHETYPE', 'AQ_OS']):
                return True
        if metadata:
            if set(metadata.keys()).intersection(['aq_domain', 'aq_sandbox', 'aq_osversion', 'aq_personality', 'aq_archetype', 'aq_os']):
                return True
        metadata = message.get("payload").get("image_meta")

        logger.debug("Image meta: %s" % message.get("payload").get("image_meta"))

        if metadata:
            if set(metadata.keys()).intersection(['AQ_DOMAIN', 'AQ_SANDBOX', 'AQ_OSVERSION', 'AQ_PERSONALITY', 'AQ_ARCHETYPE', 'AQ_OS']):
                return True
        if metadata:
            if set(metadata.keys()).intersection(['aq_domain', 'aq_sandbox', 'aq_osversion', 'aq_personality', 'aq_archetype', 'aq_os']):
                return True

        return False

    
    def on_callback(self, ch, method, properties, body):
        body = json.loads(body.decode())

        self._logger.info("ch {0}".format(ch))

        if not body:
            self._logger.info("Body of message cannot be deserialized")
            return
        self._logger.info("[X] Received message {0}".format(body))

        try:    
            if body["metadata"]["reply_required"]:

                payload = {
                    "routing_key": properties.reply_to,
                    "message_type": body["metadata"]["message_type"],
                    "args": body["message"]
                }

                try:
                    self._sensor_service.dispatch(trigger="stackstorm_send_notifications.rabbit_reply_message", payload=payload)
                finally:
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
        
            if body["oslo.message"]:  ## not clear on this and if this is actually a defining characteristic of the desired messages
            
                message = json.loads(body["oslo.message"])
            
                if is_aq_message(message):  ##should maybe check to see if the event_type of message is one of the two desired also here?
                
                    event = message.get("event_type")
                
                    payload = {
                        "event_type": event,
                        "message": message
                    }
                
                    try:
                        self._sensor_service.dispatch(trigger="stackstorm_send_notifications.aq_message", payload=payload)
                    finally:
                        self.channel.basic_ack(delivery_tag=method.delivery_tag)
                        
            else:

                payload = {
                    "message_type": body["metadata"]["message_type"],
                    "args": body["message"]
                }

                try:
                    self._sensor_service.dispatch(trigger="stackstorm_send_notifications.rabbit_message",
                                              payload=payload)
                finally:
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
        
        except Exception as e:
            logger.error("Something went wrong parsing the message: %s", e)
            logger.error(str(message))



    def setup(self):
        if self.username and self.password:
            credentials = PlainCredentials(username=self.username, password=self.password)
            connection_params = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                connection_attempts=10,
                retry_delay=2,
                heartbeat=5
            )
        else:
            connection_params = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                connection_attempts=10,
                retry_delay=2,
                heartbeat=5
            )

        # setup consume on rabbitmq queue
        self.rabbit_conn = pika.BlockingConnection(connection_params)
        self.channel = self.rabbit_conn.channel()

        # setup exchange
        self.channel.exchange_declare(
            exchange=self.exchange,
            #exchange_type=ExchangeType.direct,
            exchange_type=self.exchange_type,
            passive=False,
            durable=self.exchange_durable,
            auto_delete=False
        )

        # setup queue
        self.channel.queue_declare(queue=self.queue, auto_delete=False)
        self.channel.queue_bind(queue=self.queue, exchange=self.exchange, routing_key=self.routing_key)
        self.channel.basic_qos(prefetch_count=1)

        # setup consume
        self.channel.basic_consume(self.queue, self.on_callback)

    def update_trigger(self, trigger):
        pass

    def add_trigger(self, trigger):
        pass

    def remove_trigger(self, trigger):
        pass
