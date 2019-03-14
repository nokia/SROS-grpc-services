############################################################################
#
#   Filename:           grpc_connection.py
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

import grpc_lib

from protos_gen import gnmi_pb2 as gnmi
from protos_gen import gnmi_pb2_grpc as gnmi_stub

from collections import OrderedDict
import json
import socket

from google.protobuf import json_format

from logging import getLogger

logger = getLogger(__name__)

def create_stub(service=None, channel=None):
    return gnmi_stub.gNMIStub(channel)

yang2json_map = {
    "string":"string",
    "boolean":"boolean",
    "empty":"null",
    "enumeration":"string",
    "bits":"string",
    "int8":"number",
    "int16":"number",
    "int32":"number",
    "uint8":"number",
    "uint16":"number",
    "uint32":"number",
    "int64":"string",
    "uint64":"string",
    "decimal64":"string",
    "instance-identifier":"string"
}


def translate_path(path, delimiter='/'):
    return gnmi.Path(elem=[str_path_to_proto(element) for element in filter(None, path.split(delimiter))])


def str_path_to_proto(str_proto_el):
    # assuming gnmi path format: node_name[key1=val1][key2=val2]
    node_name, _, keys = str_proto_el.partition('[')
    if len(keys):
        # if there is no closing bracket, keys will end up empty
        keys, _, empty = keys.rpartition(']')
        if len(empty) or not len(keys):
            return dict(name=str_proto_el, key={})
        split_list = [ keyval.partition('=') for keyval in keys.split('][')]
        key_map = dict([(keyval[0], keyval[2]) for keyval in split_list])
        return dict(name=node_name, key=key_map)
    else:
        return dict(name=str_proto_el, key={})


def values_to_dict(dict_data=None, values=None, types=None):
    res = dict()
    names = [x[0] for x in values]
    vals = [x[1] for x in values]
    if not types:types = []
    for name, value, typ in zip_longest(names, vals, types):
        set_value = None
        if typ:
            json_type = yang2json_map[typ]
            if json_type == 'string':
                set_value = str(value)
            elif json_type == 'number':
                set_value = int(value)
            elif json_type == 'boolean':
                if value.lower() == 'true':
                    set_value = True
                elif value.lower() == 'false':
                    set_value = False
            elif json_type == 'null':
                set_value == None
        else:
            # we have to assume type if none was provided
            # this will support only numbers and strings 
            try:
                set_value = int(value)
                if set_value > 4294967295:
                    set_value = str(set_value)
            except ValueError:
                pass
            if not set_value:
                if value.lower() == 'true':
                    set_value = True
                elif value.lower() == 'false':
                    set_value = False
                elif value == 'null':
                    set_value = None
                else:
                    set_value = str(value)
        res[name] = set_value
    return res

class Capabilities(grpc_lib.Rpc):

    def __init__(self, *args, **kwargs):


        grpc_lib.Rpc.__init__(self, *args, **kwargs)

        self.processed_request = []
        self.stub_method = self.stub.Capabilities

        # convenience args to store version data from most recent call
        # in case the default response_processor is called
        self.api_version = None
        self.table_versions = {}

        self.gNMI_version = None

        self.response_processor = self.default_response_processor
        self.request_type = 'unary'


    def __str__(self):
        display = "\nCapabilities - {name}\n".format(name=self.name)
        if not self.processed_request:
            display += '    No requests or responses are currently tracked\n'
        else:
            for res in self.processed_request:
                display += ('\n{res}\n'.format(res=res))
        return display


    def generator(self):
        return gnmi.CapabilityRequest()


    def receiver(self):
        self.rpc_handler = self.stub_method.future(self.generator(), 
                                                   metadata = self.metadata,
                                                   timeout = self.timeout)
        self.response_processor(self.rpc_handler.result())
        self.status = 'finished'
        self.work_queue.task_done()


    def default_response_processor(self, response = None):
        self.processed_request.append(response)
        self.gNMI_version = response.gNMI_version


    def clear(self):
        self.processed_request = []


class Get(grpc_lib.Rpc):

    def __init__(self, *args, **kwargs):

        grpc_lib.Rpc.__init__(self, *args, **kwargs)

        self.processed_request = []
        self.stub_method = self.stub.Get

        self.response_processor = self.default_response_processor

        self._prefix = None
        self._path = []
        self._data_type = None
        self._encoding = None
        self._use_models = None
        self.request_type = 'unary'

        self.response = None


    def __str__(self):
        return ('REQUEST:\n{request}\n\n'
                'RESPONSE:\n{response}\n\n'
                'ERROR:\n{error}\n').format(
                    request=self.request,
                    response=self.response,
                    error=self.error)


    def generator(self):
        return self.request


    @property
    def request(self):
        return gnmi.GetRequest(
                    prefix = self._prefix,
                    path = self._path,
                    type = self._data_type,
                    encoding = self._encoding,
                    use_models = self._use_models
                  )


    def receiver(self):
        self.rpc_handler = self.stub_method.future(self.generator(),
                                                   metadata = self.metadata,
                                                   timeout = self.timeout)
        self.response_processor(self.rpc_handler.result())
        self.status = 'finished'
        self.work_queue.task_done()


    def default_response_processor(self, response = None):
        self.response = response


    def clear(self):
        self.processed_request = []


    # some of following might seem non-sense, but i feel better wrapping
    # all of them in case we some advanced parsers, more parser options etc
    # it will yield less work in cli interfaces
    def prefix(self, prefix = None, delimiter = '/'):
        self._prefix = translate_path(path = prefix,
                                      delimiter = delimiter)


    def path(self, path = None, delimiter = '/'):
        if not self._path:
            self._path = []
        self._path.append(translate_path(path = path,
                                         delimiter = delimiter))


    def data_type(self, data_type=None):
        self._data_type = data_type


    def encoding(self, encoding=None):
        self._encoding = encoding

    # TODO: convenience functions for storing data in manner feedable to set
    # set RPCs

class Set(grpc_lib.Rpc):

    def __init__(self, *args, **kwargs):

        grpc_lib.Rpc.__init__(self, *args, **kwargs)

        self.processed_request = {}
        self.stub_method = self.stub.Get

        self.response_processor = self.default_response_processor

        self._prefix = None
        self._update = None
        self._delete = None
        self._replace = None

        self.response = None

        self.request_type = 'unary'


    def __str__(self):
        return ('REQUEST:\n{request}\n\n'
                'RESPONSE:\n{response}\n\n'
                'ERROR:\n{error}\n').format(
                    request=self.request,
                    response=self.response,
                    error=self.error)

    @property
    def request(self):
        return gnmi.SetRequest(prefix = self._prefix,
                               delete = self._delete,
                               replace = self._replace,
                               update = self._update)


    def generator(self):
        return self.request


    def receiver(self):
        self.rpc_handler = self.stub_method.future(self.generator(),
                                                   metadata = self.metadata,
                                                   timeout = self.timeout)
        self.response_processor(self.rpc_handler.result())
        self.status = 'finished'
        self.work_queue.task_done()


    def default_response_processor(self, response = None):
        self.response = response

    def prefix(self, prefix = None, delimiter = '/'):
        self._prefix = translate_path(path = prefix,
                                      delimiter = delimiter)


    def update(self, operation=None, path=None, values=None, types=None, delimiter='/'):
        path = translate_path(path, delimiter=delimiter)
        if operation == 'update':
            data = values_to_dict(values=values, types=types)
            self._update.append(
                        gnmi.Update(
                            path = path,
                            val = gnmi.TypedValue(
                                            json_val = json.dumps(data).encode()
                                    )
                        )
            )
        elif operation == 'replace':
            data = values_to_dict(values=values, types=types)
            self._replace.append(
                        gnmi.Update(
                            path = path,
                            val = gnmi.TypedValue(
                                            json_val = json.dumps(data).encode()
                                    )
                        )
            )
        elif operation == 'delete':
            self._delete.append(path)
        else:
            raise ValueError('Unsupported operation <{0}>'.format(operation))

    # TODO convenience functions which will be able to load
    # messages returned (and stored) from gnmi.Get



class Subscribe(grpc_lib.Rpc):

    def __init__(self, prefix=None, mode=None, qos=None, allow_aggregation=None, encoding=None,
                 use_aliases=None, use_models=None, *args, **kwargs):

        grpc_lib.Rpc.__init__(self, *args, **kwargs)

        self.stub_method = self.stub.Subscribe
        self.target = None
        self.response_processor = self.default_response_processor

        self._subscriptions = []
        self._prefix = prefix
        self._mode = mode
        self._qos = qos
        self._allow_aggregation = allow_aggregation
        self._encoding = encoding
        self._use_aliases = use_aliases 
        self._use_models = use_models

        self.unprocessed_poll = False
        self.unprocessed_subs = False

        self._request = None

        self.request_type = 'streaming'


    def generator(self):
        while True:
            self.work_queue.get()
            self.status = 'processing'
            if self.unprocessed_poll:
                self.unprocessed_poll = False
                yield gnmi.SubscribeRequest(
                        poll = gnmi.Poll()
                    )
            if self.unprocessed_subs:
                self.unprocessed_subs = False
                yield gnmi.SubscribeRequest(
                        subscribe = self.subscription_list
                    )
            self.work_queue.task_done()


    def receiver(self):
        self.rpc_handler = self.stub_method(self.generator(),
                                            metadata = self.metadata,
                                            timeout = self.timeout)
        for msg in self.rpc_handler:
            self.response_processor(msg)
            self.status = 'waiting'
            


    def default_response_processor(self, response = None):
        logger.info(response)


    @property
    def subscription_list(self):
        return gnmi.SubscriptionList(
                    prefix = self._prefix,
                    subscription = self._subscriptions,
                    use_aliases = self._use_aliases,
                    use_models = self._use_models,
                    qos = gnmi.QOSMarking(marking=self._qos),
                    mode = self._mode,
                    encoding = self._encoding)


    def subscription(self,path=None, trigger=None, interval=None,
                     suppress_redundant=None, heartbeat_interval=None, delimiter='/'):
        self.unprocessed_subs = True
        self._subscriptions.append(
            gnmi.Subscription(
                    path=translate_path(path, delimiter=delimiter),
                    mode=trigger,
                    sample_interval=interval,
                    suppress_redundant=suppress_redundant,
                    heartbeat_interval=heartbeat_interval
                )               
            )


    def prefix(self, prefix = None, delimiter = '/'):
        self._prefix = translate_path(path = prefix,
                                      delimiter = delimiter)


    def poll(self):
        self.unprocessed_poll = True

    def json_response_processor(self, response = None):
        '''
            Translates incoming notifications to JSON and stores them in target.
        '''
        if not self.target:
            raise ValueError('self.target has to contain path to file')
        with open(self.target, 'a') as fd:
            if response.update.timestamp:
                prefix = []
                update_type = ''
                notification = {}
                context = notification
                for el in response.update.prefix.elem:
                    context[el.name] = {}
                    for el_key, el_value in el.key.items():
                        context[el.name][el_key] = el_value
                    context = context[el.name]
                for upd in response.update.update:
                    update_type = 'update'
                    for el in upd.path.elem:
                        value = json.loads(upd.val.json_val)
                        # this is very ugly hack, but until we have more
                        # advanced parser which will be able to fetch this from
                        # yang files, this will do
                        try:
                            float(value)
                            value = float(value) if '.' in value else int(value)
                        except:
                            pass
                        context[el.name] = value
                for dlt in response.update.delete:
                    update_type = 'delete'
                    for el in dlt.elem:
                        context[el.name] = {}
                        for el_key, el_value in el.key.items():
                            context[el.name][el_key] = el_value
                        context = context[el.name]
                output_msg = {}
                output_msg['notification'] = notification
                output_msg['timestamp'] = response.update.timestamp
                output_msg['update_type'] = update_type
                fd.write('{msg}\n'.format(msg=json.dumps(output_msg)))
            else:
                output_msg = {}
                output_msg['notification'] = str(response)
                output_msg['timestamp'] = response.update.timestamp
                output_msg['update_type'] = 'sync'
                fd.write('{msg}\n'.format(msg=json.dumps(output_msg)))

    def stream_response_processor(self, response = None):
        self.streamer.send(response)

    def stream(self, ip = None, port = None, protocol = None, formatting=None):
        self.streamer = NotificationStreamer(ip=ip, port=port, protocol=protocol, formatting=formatting)
        

class NotificationStreamer(object):
    '''
        Creates object which accepts protobuf messages, converts
        them to one of supported formats and sends it specified
        destination
    '''
    def __init__(self, ip=None, port=None, protocol=None,
                 formatting='json'):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.formatting = formatting
        if protocol == 'udp':
            self.socket = self.udp_socket()
            self.send = self.udp_send
        elif protocol == 'tcp':
            self.socket = self.tcp_socket()
            self.send = self.tcp_send
        else:
            raise ValueError('{0} protocol not supported in NotificationStreamer'.format(protocol))

    def output_format(self, msg=None):
        if self.formatting == 'json':
            if msg.update.timestamp:
                prefix = []
                update_type = ''
                notification = {}
                context = notification
                for el in msg.update.prefix.elem:
                    context[el.name] = {}
                    for el_key, el_value in el.key.items():
                        context[el.name][el_key] = el_value
                    context = context[el.name]
                for upd in msg.update.update:
                    update_type = 'update'
                    for el in upd.path.elem:
                        value = json.loads(upd.val.json_val)
                        # this is not optimal solution, but
                        # router can return numeric types as
                        # strings and we shouldnt convert all
                        # of them to either int or float
                        try:
                            float(value)
                            value = float(value) if '.' in value else int(value)
                        except:
                            pass
                        context[el.name] = value
                for dlt in msg.update.delete:
                    update_type = 'delete'
                    for el in dlt.elem:
                        context[el.name] = {}
                        for el_key, el_value in el.key.items():
                            context[el.name][el_key] = el_value
                        context = context[el.name]

                output_msg = {}
                output_msg['notification'] = notification
                output_msg['timestamp'] = msg.update.timestamp
                output_msg['update_type'] = update_type
                return json.dumps(output_msg)
            elif msg.sync_response:
                return json_format.MessageToJson(msg,
                                including_default_value_fields=True,
                                preserving_proto_field_name=True)


    def udp_socket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    def udp_send(self, msg=None):
        self.socket.sendto(self.output_format(msg).encode(), (self.ip, self.port))


    def tcp_socket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect()


    def tcp_send(self, msg=None):
        self.socket.send(self.output_format(msg))

        

