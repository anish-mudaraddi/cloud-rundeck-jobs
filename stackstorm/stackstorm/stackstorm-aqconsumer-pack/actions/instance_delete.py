import sys
import json
import socket
import re

from openstack_api import OScomm
from aq_api import AQcomm

from st2common.runners.base_action import Action

class InstanceDelete(Action):
    def run(self, message):
        self.logger.info("=== Received Aquilon VM delete message ===")
        self.AQcomm = AQcomm(self.config)
        self.OScomm = OScomm(self.config)
        
        project_name = message.get("_context_project_name")
        project_id = message.get("_context_project_id")
        vm_id = message.get("payload").get("instance_id")
        vm_name = message.get("payload").get("display_name")
        username = message.get("_context_user_name")
        metadata = message.get("payload").get("metadata")
        machinename = message.get("payload").get("metadata").get("AQ_MACHINENAME")
    
        self.logger.info("Project Name: %s (%s)", project_name, project_id)
        self.logger.info("VM Name: %s (%s) ", vm_name, vm_id)
        self.logger.info("Username: %s", username)
        self.logger.info("Hostnames: %s", metadata.get('HOSTNAMES'))
    
        self.logger.debug("Hostnames: %s" + metadata.get("HOSTNAMES"))
    
        for host in metadata.get("HOSTNAMES").split(","):
            try:
                self.AQcomm.delete_host(host)
            except Exception as e:
                self.logger.error("Failed to delete host: %s", e)
                self.OScomm.update_metadata(project_id,
                    vm_id, {"AQ_STATUS" : "FAILED"})
                raise Exception("Failed to delete host")
            try:
                self.AQcomm.del_machine_interface_address(host,'eth0',machinename)
            except Exception as e:
                raise Exception("Failed to delete interface address from machine  %s", e)
    
        try:
            self.AQcomm.delete_machine(machinename)
        except Exception as e:
            raise Exception("Failed to delete machine")
    
        try:
            for host in metadata.get('HOSTNAMES').split(','):
                self.AQcomm.reset_env(host,machinename)
        except Exception as e:
            self.logger.error("Failed to reset Aquilon configuration: %s", e)
            self.OScomm.update_metadata(project_id,
                vm_id, {"AQ_STATUS" : "FAILED"})
            raise Exception("Failed to reset Aquilon configuration")
    
        self.logger.info("Successfully reset Aquilon configuration")
        self.logger.info("=== Finished Aquilon deletion hook for VM %s ===", vm_name)


    def get_metadata_value(message,key):
        """
        Function which gets the value from the possible for a given metadata key
        from the possible paths in the image or instance metadata with
        the key in uppercase or lowercase
        """
        returnstring = message.get("payload").get("metadata").get(key)
        if (returnstring == None):
            returnstring = message.get("payload").get("image_meta").get(key)
            if (returnstring == None):
                returnstring = message.get("payload").get("metadata").get(key.lower())
                if (returnstring == None):
                    returnstring = message.get("payload").get("image_meta").get(key.lower())
        return returnstring    