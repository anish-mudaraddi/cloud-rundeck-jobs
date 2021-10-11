import sys
import json
import socket
import re

from openstack_api import OScomm
from aq_api import AQcomm

from st2common.runners.base_action import Action

class InstanceCreate(Action):
    def run(self, message):
        self.logger.info("=== Received Aquilon VM create message ===")
        self.AQcomm = AQcomm(self.config)
        self.OScomm = OScomm(self.config) 
         
        project_name = message.get("_context_project_name")
        project_id = message.get("_context_project_id")
        vm_id = message.get("payload").get("instance_id")
        vm_name = message.get("payload").get("display_name")
        username = message.get("_context_user_name")    

        # convert VM ip address(es) into hostnames
        hostnames = []
        for ip in message.get("payload").get("fixed_ips"):
            try:
                hostname = socket.gethostbyaddr(ip.get("address"))[0]
                hostnames.append(hostname)

            except Exception as e:
                self.logger.error("Problem converting ip to hostname", e)
        #        raise Exception("Problem converting ip to hostname")

        if len(hostnames) > 1:
            self.logger.warn("There are multiple hostnames assigned to this VM")
        elif len(hostnames) <1:
                hostname = vm_name + '.novalocal'
                hostnames.append(hostname)
        self.logger.info("Hostnames: " + ', '.join(hostnames))

        self.logger.info("Project Name: %s (%s)", project_name, project_id)
        self.logger.info("VM Name: %s (%s) ", vm_name, vm_id)
        self.logger.info("Username: %s", username)
        self.logger.info("Hostnames: " + ', '.join(hostnames))

        try:
            # add hostname(s) to metadata for use when capturing delete messages
            # as these messages do not contain ip information
            self.OScomm.update_metadata(project_id, vm_id, {"HOSTNAMES" : ', '.join(hostnames)})
        except Exception as e:
            self.logger.error("Failed to update metadata: %s", e)
            raise Exception("Failed to update metadata")
        self.logger.info("Building metadata")

        domain = get_metadata_value(message,"AQ_DOMAIN")
        sandbox =   get_metadata_value(message,"AQ_SANDBOX")
        personality =  get_metadata_value(message,"AQ_PERSONALITY")
        osversion =  get_metadata_value(message,"AQ_OSVERSION")
        archetype =  get_metadata_value(message,"AQ_ARCHETYPE")
        osname =  get_metadata_value(message,"AQ_OS")

        vcpus = message.get("payload").get("vcpus")
        root_gb = message.get("payload").get("root_gb")
        memory_mb = message.get("payload").get("memory_mb")
        uuid = message.get("payload").get("instance_id")
        vmhost = message.get("payload").get("host")
        firstip = message.get("payload").get("fixed_ips")[0].get("address")

        self.logger.info("Creating machine")

        try:
            machinename = self.AQcomm.create_machine(uuid, vmhost, vcpus, memory_mb, hostname, prefix)
        except Exception as e:
            raise Exception("Failed to create machine {0}".format(e))
            self.logger.error("Failed to create machine {0}".format(e))
        self.logger.info("Creating Interfaces")

        for index,ip in enumerate(message.get("payload").get("fixed_ips")):
                interfacename = "eth"+ str(index)
                try:
                    self.AQcomm.add_machine_interface(machinename, ip.get("address"), ip.get("vif_mac"), ip.get("label"), interfacename,
                        #socket.gethostbyaddr(ip.get("address"))[0])
                        hostnames[0])
                except Exception as e:
                    raise Exception("Failed to add machine interface %s",e)
                    self.logger.error("Failed to add machine interface %s",e)
        self.logger.info("Creating Interfaces2")

        for index,ip in enumerate(message.get("payload").get("fixed_ips")):
            if index>0:
                interfacename = "eth"+ str(index)
                try:
                    self.AQcomm.add_machine_interface_address(machinename,
                        ip.get("address"), ip.get("vif_mac"), ip.get("label"),
                        interfacename,
                        #socket.gethostbyaddr(ip.get("address"))[0])
                        hostnames[0] )
                except Exception as e:
                    raise Exception("Failed to add machine interface address %s",e)
        self.logger.info("Updating Interfaces")

        try:
            self.AQcomm.update_machine_interface(machinename,"eth0")
        except Exception as e:
            raise Exception("Failed to set default interface %s",e)
        self.logger.info("Creating Host")

        try:
            self.AQcomm.create_host(hostnames[0], machinename, sandbox, firstip, archetype, domain, personality, osname, osversion)                      # osname needs to be valid otherwise it fails - also need to pass in sandbox
        except Exception as e:
            self.logger.error("Failed to create host: %s", e)
            newmachinename=re.search("vm-openstack-[A-Za-z]*-[0-9]*", e).group(1)
            raise Exception("IP Address already exists on %s, using that machine instead", newmachinename)
            self.logger.error("IP Address already exists on %s, using that machine instead", newmachinename)
            raise Exception("Failed to create host: %s", e)

        self.OScomm.update_metadata(project_id, vm_id, {"AQ_MACHINENAME" : machinename})
        self.logger.info("Domain: %s", domain)
        self.logger.info("Sandbox: %s", sandbox)
        self.logger.info("Personality: %s", personality)
        self.logger.info("OS Version: %s", osversion)
        self.logger.info("Archetype: %s", archetype)
        self.logger.info("OS Name: %s", osname)

        # as the machine may have been assigned more that one ip address,
        # apply the aquilon configuration to all of them
        for host in hostnames:

            try:
                if sandbox:
                    self.AQcomm.aq_manage(hostname, "sandbox", sandbox)
                else:
                    self.AQcomm.aq_manage(hostname, "domain", domain)
            except Exception as e:
                self.logger.error("Failed to manage in Aquilon: %s", e)
                self.OScomm.update_metadata(project_id, vm_id, {"AQ_STATUS" : "FAILED"})
                raise Exception("Failed to set Aquilon configuration %s",e)
            try:
                self.AQcomm.aq_make(hostname, personality, osversion, archetype, osname)
            except Exception as e:
                self.logger.error("Failed to make in Aquilon: %s", e)
                self.OScomm.update_metadata(project_id, vm_id, {"AQ_STATUS" : "FAILED"})
                raise Exception("Failed to set Aquilon configuration %s",e)

        self.logger.info("Successfully applied Aquilon configuration")
        self.OScomm.update_metadata(project_id, vm_id, {"AQ_STATUS" : "SUCCESS"})

        self.logger.info("=== Finished Aquilon creation hook for VM " + vm_name + " ===")

   
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