import os
import re
from time import sleep
from datetime import datetime, timedelta
import requests
import hvac
from logging_handler import create_logger, DEBUG, INFO
import socket
from requests.adapters import HTTPAdapter
# pylint: disable-next=import-error
from requests.packages.urllib3.poolmanager import PoolManager # type: ignore
# pylint: disable-next=import-error
from requests.packages.urllib3.connection import HTTPConnection # type: ignore

VERSION = (1, 0, 1)    # updated 2024-04-28 19:51:45.446632 from : (1, 0, 0)

IP_CHECK_URL = 'http://checkip.dyndns.org/'
IP_CHECK_REGEX = r'Current IP Address:\s*([0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3})'


# Create custom pool manager so we can define different source ports for the flows
# Needed to force traffic through different paths so we have different source addresses!
class SourcePortAdapter(HTTPAdapter):
    """"Transport adapter" that allows us to set the source port."""
    def __init__(self, port=None, *args, **kwargs):
        self._source_port = port
        super(SourcePortAdapter, self).__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        pool_kwargs = kwargs if kwargs is not None else {}
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, source_address=('', self._source_port if self._source_port is not None else 0), 
            socket_options=HTTPConnection.default_socket_options + [(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),],
            **pool_kwargs)


class GetMyIpV4:
    ''' Class to get the current public IPv4 address '''
    def __init__(self, retry:int=3, timeout:int=3, retry_delay=2, url=IP_CHECK_URL, regex=IP_CHECK_REGEX, log_level=INFO):
        self.__logger = create_logger(log_level, name=self.__class__.__name__)
        self.url = url
        self.regex = regex
        self.retry = retry
        self.retry_delay = retry_delay
        self.timeout = timeout

    def ip(self, source_port:int|None=None) -> str:
        ''' Get the current IP address and return '''
        try_count = 0
        while try_count < self.retry:
            new_session = None
            try:
                self.__logger.debug(f"({try_count+1}/{self.retry}) Getting IP from: {self.url}, {'port ' + str(source_port) if source_port is not None else ''}")
                new_session = requests.Session()
                new_session.mount('http://', SourcePortAdapter(source_port))
                data = new_session.get(url=self.url, timeout=self.timeout)
                new_session.close()
                ip_regex = re.search(self.regex, data.text)
                if ip_regex:
                    self.__logger.debug(f"Public IP: {ip_regex.groups()[0]}")
                    return ip_regex.groups()[0]
            except Exception as e:
                self.__logger.warning(f"({try_count+1}/{self.retry}) Failed to get public IP. Error: {e}")
                if try_count + 1 >= self.retry:
                    raise e
                else:
                    self.__logger.info(f"Waiting {self.retry_delay} seconds before retrying...")
                    sleep(self.retry_delay)
            finally:
                if isinstance(new_session, requests.Session):
                    new_session.close()
            try_count += 1
        raise ConnectionError(f'({try_count+1}/{self.retry}) Error getting IP from {self.url}')


class AuthenticationError(Exception):
    ''' Class to represent an authentication error '''
    pass


class CredsClear:
    ''' Class to handle credentials in clear text '''
    def __init__(self, username:str, password:str):
        self.__username = username
        self.__password = password

    @property
    def creds(self):
        ''' Return the creds as a tuple of user, pass '''
        return (self.__username, self.__password)


class VaultKv2Path:
    ''' Class to represent the mount name, path, and username/password variables '''
    def __init__(self, mount:str, path:str, user_field:str='username', pass_field:str='password'):
        self.mount = mount
        self.path = path
        self.user_field = user_field
        self.pass_field = pass_field

    @property
    def config(self):
        ''' Return the KV2 path as a dict of parameters that can be passed to the read_secret function '''
        return {'mount_point': self.mount, 'path': self.path}


class CredsVaultToken(CredsClear):
    ''' class to handle credentials stored in a Hashicorp Vault password store '''
    def __init__(self, url:str, path:VaultKv2Path, token:str|None=None, ca_cert:str|None=None, renew_token=True):
        ''' If no token was provided, checks for a VAULT_TOKEN environment variable '''
        self.__path = path
        self.__client = hvac.Client(url=url, token=token if token is not None else os.environ['VAULT_TOKEN'], verify=ca_cert)
        if not self.__client.is_authenticated():
            raise AuthenticationError(f'Client Authentication failed to {url}')
        if renew_token:
            # renew the lease on the token!
            self.__client.auth.token.renew_self()

        super().__init__(*self.__get_creds())

    def __get_creds(self):
        cred_data = self.__client.secrets.kv.v2.read_secret(**self.__path.config)
        return (cred_data['data']['data'][self.__path.user_field], cred_data['data']['data'][self.__path.pass_field])


class UmbrellaException(Exception):
    ''' Class to represent an error with the Umbrella API '''
    pass

UMBRELLA_API_BASE = 'https://api.umbrella.com'
UMBRELLA_TOKEN_PATH = 'auth/v2/token'
UMBRELLA_NETWORKS = 'deployments/v2/networks'
UMBRELLA_DYNAMIC_UPDATE_URL = 'https://updates.opendns.com/nic/update'
UMBRELLA_UPDATE_CODES = {
    'badauth': 'Username and password credentials are invalid or do not match an existing Umbrella account.',
    'nohost': 'Umbrella account specified does not have a network enabled for dynamic IP updates.',
    'good': 'The update was successful or not needed (the IP address has not changed since last update). Umbrella filtering and security settings are applied as configured on this network.',
    '!yours': 'The IP address provided is part of a larger block of addresses managed by another Umbrella administrator or the IP address is being used by someone else.',
    'abuse': 'Umbrella received more than one update per minute for a set period of time.',
    '911': 'There is a problem or scheduled maintenance on the server side. Please contact Umbrella support.'
}


class UmbrellaAPI:
    ''' Class to handle calls to Cisco Umbrella API '''
    def __init__(self, hostname:str, creds:CredsClear, api_key:CredsClear, pub_ip_poller:GetMyIpV4|None=None, retry:int=3, timeout:int=3, delay=60, retry_delay=1, log_level:str=INFO, source_port:int|None=None):
        self.__logger = create_logger(log_level, name=self.__class__.__name__)
        self.hostname = hostname
        self.__creds = creds
        self.__api_key = api_key
        self.pub_ip_poller = pub_ip_poller if pub_ip_poller is not None else GetMyIpV4()
        self.retry = retry
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.delay = delay # time before retrying an update
        self.source_port = source_port
        self.__token = None
        self.__token_expires = datetime.now()

    @property
    def token_expired(self) -> bool:
        ''' Returns True if the token is expired '''
        return datetime.now() >= self.__token_expires

    def __refresh_token(self) -> bool:
        ''' Get a token using the credentials. Returns True if successful '''
        try_count = 0
        while try_count < self.retry:
            try:
                self.__logger.debug(f"({try_count+1}/{self.retry}) Getting Umbrella Token...")
                data = requests.post(url=f"{UMBRELLA_API_BASE}/{UMBRELLA_TOKEN_PATH}",
                                     auth=self.__api_key.creds, data={"grant_type": "client_credentials"},
                                     timeout=self.timeout)
                if data.status_code == 200:
                    self.__token = data.json()['access_token']
                    self.__token_expires = datetime.now() + timedelta(seconds=data.json()['expires_in'])
                    return True
            except Exception as e:
                self.__logger.warning(f"({try_count+1}/{self.retry}) Failed to get Umbrella token. Error: {e}")
                if try_count + 1 >= self.retry:
                    raise e
                else:
                    self.__logger.info(f"Waiting {self.retry_delay} seconds before retrying token refresh...")
                    sleep(self.retry_delay)
            try_count += 1
        return False

    def get_network_list(self) -> list:
        ''' Get a list of the networks from Umbrella '''
        if self.token_expired:
            if not self.__refresh_token():
                raise UmbrellaException('Unable to refresh Umbrella Token')
        try_count = 0
        while try_count < self.retry:
            try:
                self.__logger.debug(f"({try_count+1}/{self.retry}) Getting Umbrella Network List...")
                data = requests.get(url=f"{UMBRELLA_API_BASE}/{UMBRELLA_NETWORKS}",
                                     headers={'authorization': "Bearer " + str(self.__token)},
                                     timeout=self.timeout)
                if data.status_code == 200:
                    return data.json()
            except Exception as e:
                self.__logger.warning(f"({try_count+1}/{self.retry}) Failed to get Umbrella Network List. Error: {e}")
                if try_count + 1 >= self.retry:
                    raise e
                else:
                    self.__logger.info(f"Waiting {self.retry_delay} seconds before retrying get network list...")
                    sleep(self.retry_delay)
            try_count += 1
        return []

    def get_network(self, name:str|None=None) -> dict:
        ''' Get a specific network '''
        name = name if name is not None else self.hostname
        for network in self.get_network_list():
            if name.lower() == network.get('name', '').lower():
                self.__logger.debug(f"'{name}' matched network: {network}")
                return network
        raise UmbrellaException(f'Network "{name}" not found')

    def ip_match(self, name:str|None=None, source_port:int|None=None) -> bool:
        ''' Returns True if the IP of the network matches the current public IP '''
        name = name if name is not None else self.hostname
        return self.get_network(name=name).get('ipAddress') == self.pub_ip_poller.ip(source_port if source_port is not None else self.source_port)

    def update_ip(self, name:str|None=None, source_port:int|None=None) -> bool:
        ''' Update the IP if required, return True if successful or not needed '''
        name = name if name is not None else self.hostname
        if self.ip_match(name=name, source_port=source_port if source_port is not None else self.source_port):
            self.__logger.info(f"'{name}' IP already up to date. No update required. Current IP: {self.get_network(name=name).get('ipAddress')}")
            return True
        try_count = 0
        while try_count < self.retry:
            new_session = None
            try:
                self.__logger.debug(f"{name}: ({try_count+1}/{self.retry}) Updating public ip for '{name}'...")
                new_session = requests.Session()
                new_session.mount('https://', SourcePortAdapter(source_port if source_port is not None else self.source_port))
                data = new_session.put(url=UMBRELLA_DYNAMIC_UPDATE_URL + '?hostname=' + name,
                                    auth=self.__creds.creds,
                                    timeout=self.timeout)
                new_session.close()
                if data.status_code == 200:
                    self.__logger.debug(f"{name}: Update response: {data.text}")
                    response = data.text.split()
                    if response[0] == 'good':
                        self.__logger.info(f"{name}: Update for '{name}' successful. New IP: {response[1]}")
                        return True
                    self.__logger.warning(f"{name}: ({try_count+1}/{self.retry}) Failed to update '{name}'. Error code: {response[0]}. {UMBRELLA_UPDATE_CODES[response[0]]}")
                    return False
            except Exception as e:
                self.__logger.warning(f"{name}: ({try_count+1}/{self.retry}) Failed to update public ip for '{name}'. Error: {e}")
                if try_count + 1 >= self.retry:
                    raise e
                else:
                    self.__logger.info(f"{name}: Waiting {self.retry_delay} seconds before retrying update ip...")
                    sleep(self.retry_delay)
            finally:
                if isinstance(new_session, requests.Session):
                    new_session.close()
            self.__logger.debug(f"{name}: Waiting {self.delay} seconds before next attempt...")
            sleep(self.delay)
            try_count += 1
        return False