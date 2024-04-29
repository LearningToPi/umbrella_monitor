import argparse
from umbrella_monitor import *
from .toml_config_mgr import TomlConfigMgr, url
from logging_handler import create_logger, INFO

LOG_LEVEL = INFO

TOML_CONFIG = {
    "general": {
        "log_level": {
            "type": str,
            "default": "INFO",
            "required": False,
            "help": "Log level to use for all classes (i.e. 'INFO', 'DEBUG', 'WARNING')"
        }
    },
    "vault_config": {
        "url": {
            "type": url,
            "help": "Vault main URL address (i.e. 'https://vault.domain.com')",
            "required": True
        },
        "token": {
            "type": str,
            "required": True,
            "help": "Vault token to used access all vault objects"
        },
        "ca_cert": {
            "type": str,
            "required": False,
            "help": "Path to CA certificate to validate the Vault server SSL cert against"
        }
    },
    "umbrella_acct": {
        "mount": {
            "type": str,
            "required": True,
            "help": "Name of the vault mount where KV pairs are stored"
        },
        "path": {
            "type": str,
            "required": True,
            "help": "Path in Vault mount where the Umbrella username/password is stored (CASE SENSITIVE!)"
        },
        "user_field": {
            "type": str,
            "required": False,
            "default": "username",
            "help": "Field in KV Path that holds the username (defaults to username)"
        },
        "pass_field": {
            "type": str,
            "required": False,
            "default": "password",
            "help": "Field in KV Path that holds the password (defaults to password)"
        }
    },
    "umbrella_api_key": {
        "mount": {
            "type": str,
            "required": True,
            "help": "Name of the vault mount where KV pairs are stored"
        },
        "path": {
            "type": str,
            "required": True,
            "help": "Path in Vault mount where the Umbrella username/password is stored (CASE SENSITIVE!)"
        },
        "user_field": {
            "type": str,
            "required": False,
            "default": "username",
            "help": "Field in KV Path that holds the username (defaults to username)"
        },
        "pass_field": {
            "type": str,
            "required": False,
            "default": "password",
            "help": "Field in KV Path that holds the password (defaults to password)"
        }
    },
    "umbrella": {
        "hostname": {
            "type": str,
            "required": True,
            "help": "Network name / hostname configured in Umbrella.  MUST MATCH AND HAVE DYNAMIC IP SET!"
        },
        "source_port": {
            "type": int,
            "required": False,
            "default": None,
            "help": "Source port to use for outbound IP check and update to Umbrella. Useful for routing based on source port."
        }
    }
}

if __name__ == '__main__':
    logger = create_logger(name='UmbrellaMonitor')
    try:
        # setup the argument parser
        parser = argparse.ArgumentParser(prog="python3 -m umbrella_monitor", description="Python script to check and update the dynamic IP of an Umbrella network")
        run_config = TomlConfigMgr(**TOML_CONFIG)
        run_config.update_argparser(parser, prepend_sections=True)

        parser.add_argument('--config', '-c', required=False, type=str, default=None,
                            help="JSON config file to load. See README.md file for contents.")
        parser.add_argument('--print-version', '-vv', required=False, action='store_true', default=False,
                            help="Print the current version and quit.")

        args = vars(parser.parse_args())

        if args.get('print_version'):
            print("Python script to check and update the dynamic IP of an Umbrella network")
            print(f"Version: {str(VERSION[0])}.{str(VERSION[1])}.{str(VERSION[2])}{'-' + str(VERSION[3]) if len(VERSION) >= 4 else ''}") # type: ignore
            print("Use command line parameter '-h' or see the README.md file in github for usage details: https://github.com/learningtopi/umbrella_monitor/")
            quit(0)

        # if a config file was provided, load the config file
        if args.get('config') is not None:
            run_config.load_toml(str(args.get('config')))

        # load all passed parameters
        for section in run_config.sections():
            for key in run_config.section_keys(section):
                run_config.update(section, key, args.get(section + '_' + key))
                run_config.update(section, key, args.get(key))

        # Create all the objects
        creds_umbrella = CredsVaultToken(**run_config.config()['vault_config'],
                                        path=VaultKv2Path(**run_config.config()['umbrella_acct']))
        creds_api = CredsVaultToken(**run_config.config()['vault_config'],
                                    path=VaultKv2Path(**run_config.config()['umbrella_api_key']))
        pub_ip_poller = GetMyIpV4(log_level=run_config.get('general', 'log_level'))
        umbrella = UmbrellaAPI(**run_config.config()['umbrella'], creds=creds_umbrella, pub_ip_poller=pub_ip_poller, api_key=creds_api,
                               log_level=run_config.get('general', 'log_level'))

        # update the umbrella network IP
        umbrella.update_ip()

        # verify update was successful
        if not umbrella.ip_match():
            logger.error(f"Umbrella update for {umbrella.hostname} not successful. Umbrella info: {umbrella.get_network()}")
    except Exception as e:
        logger.error(f"Error updating Umbrella IP: {e.__class__.__name__}: {e}")
