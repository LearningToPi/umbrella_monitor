import unittest
import json
from time import sleep
from logging_handler import create_logger, INFO, DEBUG # pylint: disable=unused-import
import requests
import umbrella_monitor

logger = create_logger(DEBUG, name='UpdateTest')

# load config file
with open('local/config.json', 'r', encoding='utf-8') as input_file:
    config_data = json.load(input_file)



class UmbrellaUpdaterTest(unittest.TestCase):
    def test_1_update_test(self):
        # create objects
        creds_umbrella = umbrella_monitor.CredsVaultToken(**config_data['vault_config'],
                                                        path=umbrella_monitor.VaultKv2Path(**config_data['vault_path_umbrella_acct']))
        creds_api = umbrella_monitor.CredsVaultToken(**config_data['vault_config'],
                                                    path=umbrella_monitor.VaultKv2Path(**config_data['vault_path_umbrella_api_key']))
        pub_ip_poller = umbrella_monitor.GetMyIpV4(log_level=DEBUG)
        umbrella = umbrella_monitor.UmbrellaAPI(**config_data['umbrella'], creds=creds_umbrella, pub_ip_poller=pub_ip_poller, api_key=creds_api)

        # check if the public address already matches
        logger.info(f"Pre Test state: IP's match: {umbrella.ip_match()}")

        # get the public IP for each of the streams
        x = 0
        for x in range(len(config_data['source_ports'])):
            source_port = config_data['source_ports'][x]['port']
            # Check if the IP matches
            logger.info(f"Port: {config_data['source_ports'][x]['port']}, Pre update state: IP's match: {umbrella.ip_match(source_port=source_port)}")

            # call to update
            umbrella.update_ip(source_port=source_port)
            logger.info(f"Port: {config_data['source_ports'][x]['port']}, Post update state: IP's match: {umbrella.ip_match(source_port=source_port)}")
            if config_data['source_ports'][x]['should_pass']:
                self.assertTrue(umbrella.ip_match(source_port=source_port))
            else:
                self.assertFalse(umbrella.ip_match(source_port=source_port))

            # if there is another stream to test, wait for 90 seconds so we don't get banned
            x += 1
            if x < len(config_data['source_ports']):
                logger.info("Waiting for 60 seconds for next iteration to prevent getting banned...")
                sleep(60)

if __name__ == '__main__':
    unittest.main()
