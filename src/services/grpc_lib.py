############################################################################
#
#   Filename:           grpc_lib.py
#
#   Author:             Martin Tibensky
#   Created:            Fri Feb  8 16:09:22 CET 2019
#
#   Description:        .
#
#
############################################################################
#
#              Copyright (c) 2019 Nokia
#
############################################################################

from grpc import RpcError
from grpc._cython.cygrpc import CompressionAlgorithm
from grpc import ssl_channel_credentials, insecure_channel, secure_channel

from collections import OrderedDict
from threading import Thread
from Queue import Queue
import time

from google.protobuf import json_format
import pickle

from logging import getLogger

logger = getLogger(__name__)

class Channel:

    """Create channel object that can be passed to stub.

    gNOI CertificateManagement will be integrated as additional
    option for secure connection in this class.

    Attributes:
        username (str): Username which will be used in each RPC.
        password (str): Password which will be used in each RPC.
        ip (str): ipv4 or ipv6 addr of target.
        port (str): Port number of target.
        auth_type (str): You can specify unsecured, server or mutual
            connection. Unsecured will try to create http2 channel
            directly over TCP connection. Server and mutual will use TLS as
            secure protocol but requires setting root_cert(server) or
            root_cert, key and cert(mutual).
        root_cert (str): Path to CA cert.
        key (str): Path to private key.
        cert (str): Path to certificate signed by CA
        compression (str): Compression algorithm to use. Defaults to deflate.
        try_to_connect (bool): When set to true, the channel will try to connect
            immediately after creation, otherwise it will typically wait for first
            RPC call. Defaults to false.
    """

    def __init__(self, username = None, password = None, ip = None,
                port = None, auth_type = None, transport = None,
                root_cert = None, key = None, cert = None,
                compression = 'deflate', try_to_connect = False):
        self.username = username
        self.password = password
        self.ip = ip
        self.port = port
        self.auth_type = auth_type
        self.transport = transport
        self.root_cert = root_cert
        self.key = key
        self.cert = cert
        self.compression = compression
        self.try_to_connect = try_to_connect
        self.channel_state = None


        # later in game we might consider prepending this automatically
        # as channel opt, but for now, we will specify it within each
        # message separately
        self.metadata = [('username', username), ('password', password)]

        channel_opts = [('grpc.default_compression_algorithm', getattr(CompressionAlgorithm, compression.lower()))]

        self.addr_type = {True: "ipv4", False: "ipv6"}[self.ip.find(":") == -1]
        if self.addr_type == "ipv4":
            target = str(ip) + ':' + str(port)
        elif self.addr_type == "ipv6":
            target = "[" + str(ip) + "]" + ':' + str(port)
        else:
            raise ValueError('Received unhandled ip type <{type}> from address <{addr}>'.format(type=self.addr_type,addr=self.ip))

        if transport == 'secure':
            root_certificates = open(root_cert, 'rb').read() if root_cert else None
            private_key = open(key, 'rb').read() if key else None
            certificate_chain = open(cert, 'rb').read() if cert else None
            credentials = ssl_channel_credentials(root_certificates=root_certificates,
                                                  private_key=private_key,
                                                  certificate_chain=certificate_chain)
            self.channel = secure_channel(target=target, credentials=credentials, options=channel_opts)
        elif transport == 'unsecure':
            self.channel = insecure_channel(target=target, options=channel_opts)
        else:
            raise ValueError('Unsupported transport: <{trans}>'.format(trans=transport))

        self.channel.subscribe(self.channel_state_cb, try_to_connect = self.try_to_connect)

    def __str__(self):
        return ('\nChannel:\n'
                '   ip: {ip}\n'
                '   port: {port}\n'
                '   username: {username}\n'
                '   root_cert: {root_cert}\n'
                '   cert: {cert}\n'
                '   key: {key}\n'
                '   auth_type: {auth_type}\n'
                '   compression: {compression}\n'
                '   try_to_connect: {try_to_connect}\n'
                '   channel_state: {channel_state}').format(
                        ip=self.ip,
                        port=self.port,
                        username=self.username,
                        root_cert=self.root_cert,
                        cert=self.cert,
                        key=self.key,
                        auth_type=self.auth_type,
                        compression=self.compression,
                        try_to_connect=self.try_to_connect,
                        channel_state=self.channel_state)


    def channel_state_cb(self, connectivity):
        self.channel_state = connectivity


class RpcManager:
    """Create manger which will register all processed RPCs.

    """

    def __init__(self, rpc_types = None):
        self.rpc_types = rpc_types
        self.rpcs = OrderedDict()
        for rpc_type in self.rpc_types:
            self.rpcs[rpc_type] = OrderedDict()

    def __str__(self):
        rpcs = ''
        for rpc_type in self.rpc_types:
            rpcs += '\n'
            rpcs += '{0}\n'.format(rpc_type)
            if not self.rpcs[rpc_type]:
                rpcs += '   {0}\n'.format('No RPCs of this type found')
                continue
            for rpc_msg in self.rpcs[rpc_type]:
                rpc = self.rpcs[rpc_type][rpc_msg]
                rpcs += '   {0}:\n'.format(self.rpcs[rpc_type][rpc_msg].name)
                rpcs += '       status:     {0}\n'.format(rpc.status)
                rpcs += '       delimiter:  {0}\n'.format(rpc.delimiter)

        return rpcs

    def add_rpc(self, rpc):
        self.rpcs[rpc.rpc_type][rpc.name] = rpc


    def get_rpc(self, type=None, name=None):
        try:
            rpc = str(self.rpcs[type][name])
        except KeyError:
            raise ValueError('Rpc with type {type} and name {name} doesnt exist'.format(
                                                            type=type, name=name))
        return rpc


    def add(self, rpc=None):
        """Add rpc to manager.

        Args:
            rpc: Each rpc instance that would like to be managed by
                RpcManager must have rpc_type and name attributes which
                are used for aggregating similar RPCs.
        """
        if rpc.rpc_type not in self.rpcs:
            self.register_type(rpc.rpc_type)
        self.rpcs[rpc.rpc_type][rpc.name] = rpc


    def destroy(self, rpc_type=None, name=None, cancel=True):
        """Remove rpc from manager, call cancel method if the.

        Args:
            rpc_type (str): Alternative to passing rpc instance is specifing rpc_type and name.
            name (str): Alternative to passing rpc instance is specifing rpc_type and name.
            cancel (bool): if set to True(default), cancel method of rpc is automatically called
                before destroying the object. If cancel method is not implemented, nothing happens.
        """
        if (cancel == True and
            hasattr(self.rpcs[rpc_type][name], 'cancel') and
            self.rpcs[rpc_type][name].rpc_handler):
            # we can cancel
            self.rpcs[rpc_type][name].cancel()
        del self.rpcs[rpc_type][name]


class Rpc:

    supported_formats = ['dict', 'string', 'json']

    def __init__(self, stub=None, name=None, rpc_type=None,
                 metadata=None, delimiter=None, timeout=None,
                 server_addr=None, server_port=None,
                 *args, **kwargs):
        self.stub = stub
        self.rpc_type = rpc_type
        self.name = name

        self.metadata = metadata
        self._timeout = timeout
        self.error = None

        self.status = 'init'
        self.delimiter = delimiter
        self.worker = None
        self.rpc_handler = None

        self.work_queue = Queue()
        self.work_status = 'idle'

        self.default_delimiter = '/'

        self.request_handler = None #gnmi.SetRequest
        self.response_handler = None #gnmi.SetResponse

        self.server_addr = server_addr
        self.server_port = server_port


    def __str__(self):
        raise NotImplementedError


    def timeout(self, timeout=None):
        self._timeout = timeout


    def execute(self, timeout=None):
        # if some handler is alive, the rpc is already running
        # and request generator will consume any additional requests
        # we will just flip consume flag here and feed work to queue
        # in case of streaming request, we dont need to restart the thread
        self.work_queue.put(time.time())
        if self.worker and self.request_type == 'streaming' and self.status != "finished":
            return
        self.worker = Thread(target=self.run)
        self.worker.daemon = True
        self.worker.start()


    def run(self):
        self.status = 'running'
        try:
            self.receiver()
        except RpcError as rpc_error:
            logger.error('{code} {details}'.format(code=rpc_error.code(),
                                                   details=rpc_error.details()))
            self.error = rpc_error
        except Exception as e:
            logger.error('Unhandled exception happened')
            logger.error(str(e))
            self.error = e
            self.status = 'erroneous'
            raise
        finally:
            self.work_queue = Queue()
            self.rpc_handler = None
        self.status = 'finished'


    def response_streaming(self):
        pass


    def cancel(self):
        """
            Attempts to cancel the RPC in case it is running.
        """
        if self.rpc_handler:
            self.rpc_handler.cancel()


    def wait(self, timeout=None):
        """Wait until all requests receive response.

            If timeout in seconds is specified, the function will
            block until the queue is empty or timeout expires.
            None is returned in both cases, so if user needs to know
            if all requests were processed, he has to check the queue
            himself. This is in line with how thread join works.

        """
        if timeout:
            stop = time.time() + timeout
            while (self.work_queue.unfinished_tasks and
                   time.time() < stop):
                time.sleep(0.1)
        else:
            self.work_queue.join()


    def parse(self, target=None, msg=None, format=None, handler=None):
        """Parse message from format to python object

        Reutrns python object which represents python message.

        Args:
            target (str): Path to file where serialized message will
                be stored.
            msg: Object which contains protobuf message.
            format: One of formats listed in Rpc.supported_formats
            handler: message handler, typically request or response message
                defined under service rpc definition.
        """

        if format not in Rpc.supported_formats:
            raise ValueError('{format} is not supported, use one of {supported}'.format(
                            format= format, supported=Rpc.supported_formats))


        if target:
            with open(target, 'rb') as fd:
                if format in ['string', 'json']:
                    msg = fd.read()
                elif format in ['dict']:
                    msg = pickle.load(fd)

        if format == 'string':
            result = handler().ParseFromString(msg)
        elif format == 'json':
            result  = json_format.Parse(msg, handler())
        elif format == 'dict':
            result = json_format.ParseDict(msg, handler())

        return result

    def serialize(self, target=None, msg=None, format=None):
        """Serialize message from python object to format.

        Returns messsage in given format or if target is speficied, the
        message is dumped to given path.

        Args:
            target (str): Path to file where serialized message will
                be stored. If none, the message will be returned.
            msg: Object which contains protobuf message.
            format: One of formats listed in Rpc.supported_formats

        """

        if format not in Rpc.supported_formats:
            raise ValueError('{format} is not supported, use one of {supported}'.format(
                            format= format, supported=Rpc.supported_formats))

        if format == 'string':
            result  = msg.SerializeToString()
        elif format == 'json':
            result = json_format.MessageToJson(msg,
                                including_default_value_fields=True,
                                preserving_proto_field_name=True)
        elif format == 'dict':
            result =  json_format.MessageToDict(msg,
                                    including_default_value_fields=True,
                                    preserving_proto_field_name=True)

        if target:
            with open(target, 'wb') as fd:
                if format in ['string', 'json']:
                    msg = fd.write(result)
                elif format in ['dict']:
                    msg = pickle.dump(result, fd)
        else:
            return result


