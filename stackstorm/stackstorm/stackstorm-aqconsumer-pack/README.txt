This pack was created to replace the following service for COG team, STFC RAL:

  https://github.com/stfc/SCD-OpenStack-Utils/tree/hook-changes2/OpenStack-Rabbit-Consumer

In this form, it uses the "rabbit_sensor" in the "stackstorm-notifications-pack" to consume rabbit messages,
and it sets off a specific trigger "stackstorm_send_notifications.aq_message" when it identifies it is a message for this service.

Then rules in this pack will pick up that trigger, and set off one of two actions (create or delete instance) based on the "event_type" 
criteria from the message.

Two configs need to be set, one in the notifications pack for the rabbitmq settings, and the rest in this pack for all the aquilon/
openstack/keberos settings. Each pack specifies the contents of these config files in the "config.schema.yaml" file.

Not sure where to actually store the configs in the end, but they follow standard yaml format. 
Documentation says store at "/opt/stackstorm/configs<pack-name>.yaml", but also they need to be registered:
  https://docs.stackstorm.com/reference/pack_configs.html?highlight=config%20yaml