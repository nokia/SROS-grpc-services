############################################################################
#
#   Filename:           rib_service.py
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

from grpc_lib import Rpc

from protos_gen import nokia_rib_api_pb2 as rib
from protos_gen import nokia_rib_api_pb2_grpc as rib_stub
from google.protobuf import json_format

from collections import OrderedDict

def create_stub(service=None, channel=None):
    return rib_stub.RibApiStub(channel)

class GetVersion(Rpc):
    '''
        Implements Nokia.SROS.RibApi.GetVersion unary rpc

        Default response_processor stores api_version in object attribure with
        same name. operational_tables are stored in same named dictionary where key
        is table id and value is table version.
    '''


    def __init__(self, *args, **kwargs):

        Rpc.__init__(self, *args, **kwargs)

        self.processed_request = []
        self.stub_method = self.stub.GetVersion

        # convenience args to store version data from most recent call
        # in case the default response_processor is called
        self.api_version = None
        self.table_versions = {}

        self.response_processor = self.default_response_processor

        self.request_type = 'unary'


    def __str__(self):
        display = "GetVersion - {name}\n".format(name=self.name)
        if not self.processed_request:
            display += '    No requests or responses are currently tracked\n'
        else:
            for res in self.processed_request:
                display += ('\n{res}\n'.format(res=res))
        return display


    def generator(self):
        return rib.VersionRequest()


    def receiver(self):
        self.rpc_handler = self.stub_method.future(self.generator(), 
                                                   metadata = self.metadata,
                                                   timeout = self.timeout)
        self.response_processor(self.rpc_handler.result())
        self.status = 'finished'
        self.work_queue.task_done()


    def default_response_processor(self, response = None):
        self.processed_request.append(response)
        self.api_version = response.api_version
        for table in response.operational_tables:
            self.table_versions[table.id] = table.version


    def clear(self):
        self.processed_request = []


class Modify(Rpc):
    '''
        Implements Nokia.SROS.RibApi.Modify bidirectional streaming rpc.
        
        TODO: move this from docstring to more appropriate place
        One way to track request-response is via storing all data in
        dict and map id in rpcs to key in dics. This enables fast lookup of
        request-response pairs. And if there will be need in future, we can expose
        this to user to more easily implement scenarios where request must be
        based on previous response or the request has to wait for certain
        response.
    '''


    def __init__(self, *args, **kwargs):

        Rpc.__init__(self, *args, **kwargs)

        self.request = OrderedDict()
        self.processed_request = OrderedDict()
        self.response = OrderedDict()
        self.request_counter = 0
        self.stub_method = self.stub.Modify
        self.response_processor = self.default_response_processor

        self.request_type = 'streaming'


    def __str__(self):
        display = 'Modify - {name}\n'.format(name=self.name)
        if not self.processed_request:
            display += '    No requests or responses are currently tracked\n'
        else:
            for pair_id in self.processed_request:
                display += ('======= id: {id} =======\n'
                            '==request {id}:\n'
                            '{req}\n\n'
                            '==response {id}:\n'
                            '{res}\n\n'
                            '======= id: {id} =======\n').format(
                                id = pair_id,
                                req = self.processed_request[pair_id]['request'],
                                res = self.processed_request[pair_id]['response'])
        display += '\nError:\n{err}'.format(err = self.error)
        return display


    def request_id(self):
        self.request_counter += 1
        return self.request_counter


    def generator(self):
        '''
            Each time someone decides to put some work in queue, we yield all
            collected requests.
        '''
        while True:
            self.work_queue.get()
            self.status = 'processing'
            for request_id in self.request:
                self.processed_request[request_id] = {}
                self.processed_request[request_id]['request'] = self.request[request_id]
                self.processed_request[request_id]['response'] = None
            yield rib.ModifyRequest(request=self.request.values())
            self.request.clear()


    def receiver(self):
        self.rpc_handler = self.stub_method(self.generator(),
                                            metadata = self.metadata,
                                            timeout = self.timeout)
        for msg in self.rpc_handler:
            self.response_processor(msg)
            self.status = 'waiting'
            self.work_queue.task_done()


    def default_response_processor(self, response = None):
        for result in response.result:
            self.processed_request[result.id]['response'] = response


    def clear(self, request=True, response=True, error=True):
        '''
            Clears data gathered by this rpc by setting them
            to their initial value.

            Args:
                request (bool) - clears request, defaults to True
                response (bool) - clears response, defaults to True
                error (bool) - clears error, defaults to True
        '''
        self.wait()
        if request:
            self.request = OrderedDict()
        if response:
            self.processed_request = OrderedDict()
        if error:
            self.error = None


    def get_request(self, format=None, request_id=None):
        '''
            Returns Modify.ModifyRequest in one of given formats.
            Throws KeyError in case no such request is present.

            Args:
                format (str): json, proto, dict or string. Defaults to json.
                request_id (int): Modify.ModifyRequest.Request.id
        '''
        supported_formats = ['json', 'proto', 'dict', 'string']
        if format not in supported_formats:
            raise ValueError('{format} is not supported use one of {supported}'.format(
                                                                    format=format,
                                                                    supported=supported_formats))

        msg = rib.ModifyRequest(self.processed_request[request_id]['request'])
        if format == 'proto':
            return msg
        elif format == 'json':
            return json_format.MessageToJson(msg,
                                             including_default_value_fields=True,
                                             preserving_proto_field_name=True)
        elif format == 'dict':
            return json_format.MessageToDict(msg,
                                             including_default_value_fields=True,
                                             preserving_proto_field_name=True)
        elif format == 'str':
            return str(msg)


    def get_response(self, format=None):
        '''
            Returns Modify.ModifyResponse in one of given formats.
            Throws KeyError in case no such request is present.

            Args:
                format (str): json, proto, dict or string. Defaults to json.
                request_id (int): Modify.ModifyResponse.Result.id
        '''
        supported_formats = ['json', 'proto', 'dict', 'string']
        if format not in supported_formats:
            raise ValueError('{format} is not supported, use one of {supported}'.format(
                                                                     format=format,
                                                                     supported=supported_formats))
        msg = rib.ModifyRequest(self.processed_request[request_id]['response'])
        if format == 'proto':
            return msg
        elif format == 'json':
            return json_format.MessageToJson(msg,
                                             including_default_value_fields=True,
                                             preserving_proto_field_name=True)
        elif format == 'dict':
            return json_format.MessageToDict(msg,
                                             including_default_value_fields=True,
                                             preserving_proto_field_name=True)
        elif format == 'str':
            return str(msg)


    def route(self, id=None, operation=None, table=None, key_prefix=None, key_preference=None,
              rtm_preference=None, metric=None, tunnel_next_hop=None, json=None):
        '''
            Constructs ModifyRequest with RouteTableEntry for add and replace operations and
            RouteTableEntryKey for delete operation and adds it to request queue.

            Args:
                id (int): mandatory argument for ModifyRequest
                operation (str): oneof add, replace, delete
                table (str): oneof ipv4, ipv6
                key_prefix (str): ipv4 or ipv6 address
                key_preference (int): ordering preference
                rtm_preference (int): route table manager preference
                metric (int): configured tunnel metric to use
                tunnel_next_hop (str): ip address to use as nexthop
                json (str): whole message can be passed as json formatted sttring,
                    which needs to be enetered as valid json representation of
                    ModifyRequest.Request
        '''

        if json:
            msg = json_format.Parse(json, rib.ModifyRequest.Request())
        else:
            if id == None:
                id = self.request_id()
            if operation in ['add', 'replace']:
                table_entry = rib.RouteTableEntry(
                                entry_key = rib.RouteTableEntryKey(
                                    prefix = key_prefix,
                                    preference = key_preference
                                ),
                                rtm_preference = rtm_preference,
                                metric = metric,
                                tunnel_next_hop = tunnel_next_hop
                              )
                if table == 'ipv4' and operation == 'add':
                    msg = rib.ModifyRequest.Request(id=id,ipv4_route_ADD = table_entry)
                elif table == 'ipv4' and operation == 'replace':
                    msg = rib.ModifyRequest.Request(id=id,ipv4_route_REPLACE = table_entry)
                elif table == 'ipv6' and operation == 'add':
                    msg = rib.ModifyRequest.Request(id=id,ipv6_route_ADD = table_entry)
                elif table == 'ipv6' and operation == 'replace':
                    msg = rib.ModifyRequest.Request(id=id,ipv6_route_REPLACE = table_entry)
                else:
                    raise ValueError('Invalid combination of table and operation: <{table}:{operation}>'.format(
                                                                                    table=table,
                                                                                    operation=operation))
            elif operation == 'delete':
                if table == 'ipv4':
                    msg = rib.ModifyRequest.Request(
                                                id=id,
                                                ipv4_route_DELETE = rib.RouteTableEntryKey(
                                                            prefix = key_prefix,
                                                            preference = key_preference
                                                )
                                             )
                elif table == 'ipv6':
                    msg = rib.ModifyRequest.Request(
                                                id=id,
                                                ipv6_route_DELETE = rib.RouteTableEntryKey(
                                                            prefix = key_prefix,
                                                            preference = key_preference
                                                )
                                            )
                                        
                else:
                    raise ValueError('Invalid combination of table and operation: <{table}:{operation}>'.format(
                                                                                    table=table,
                                                                                    operation=operation))

            else:
                raise ValueError('Unkown operation request <{0}>, valid operations: {1}'.format(operation,
                                                                                                ['add', 'replace', 'delete']))

        self.request[id] = msg
        return msg.id


    def tunnel(self, id=None, operation=None, table=None, key_endpoint=None,
               key_preference=None, ttm_preference=None, metric=None, json=None):
        '''
            Constructs ModifyRequest with TunnelTableEntry message and adds it to request queue.

            Args:
                id (int): mandatory argument for ModifyRequest
                operation (str): oneof add, replace, delete
                table (str): oneof ipv4, ipv6
                key_endpoint (str): ipv4 or ipv6 address
                key_preference (int): ordering preference
                ttm_preference (int): tunnel table manager preference
                metric (int): tunnel table manager metric, used as a tiebreaker
                    between duplicate entries.
                json (str): whole message can be passed as json formatted sttring,
                    which needs to be enetered as valid json representation of
                    ModifyRequest.Request
        '''

        if json:
            msg = json_format.Parse(json, rib.ModifyRequest.Request())
        else:
            if operation in ['add', 'replace']:
                table_entry = rib.TunnelTableEntry(
                                entry_key = rib.TunnelTableEntryKey(
                                    endpoint = key_endpoint,
                                    preference = key_preference
                                ),
                                ttm_preference = ttm_preference,
                                metric = metric
                              )
                if table == 'ipv4' and operation == 'add':
                    msg = rib.ModifyRequest.Request(id=id,ipv4_tunnel_ADD = table_entry)
                elif table == 'ipv4' and operation == 'replace':
                    msg = rib.ModifyRequest.Request(id=id,ipv4_tunnel_REPLACE = table_entry)
                elif table == 'ipv6' and operation == 'add':
                    msg = rib.ModifyRequest.Request(id=id,ipv6_tunnel_ADD = table_entry)
                elif table == 'ipv6' and operation == 'replace':
                    msg = rib.ModifyRequest.Request(id=id,ipv6_tunnel_REPLACE = table_entry)
                else:
                    raise ValueError('Invalid combination of table and operation: <{table}:{operation}>'.format(
                                                                                    table=table,
                                                                                    operation=operation))
            elif operation == 'delete':
                if table == 'ipv4':
                    msg = rib.ModifyRequest.Request(
                                                id=id,
                                                ipv4_tunnel_DELETE = rib.TunnelTableEntryKey(
                                                            endpoint = key_endpoint,
                                                            preference = key_preference
                                                )
                                             )
                elif table == 'ipv6':
                    msg = rib.ModifyRequest.Request(
                                                id=id,
                                                ipv6_tunnel_DELETE = rib.TunnelTableEntryKey(
                                                            endpoint = key_endpoint,
                                                            preference = key_preference
                                                )
                                            )
                                        
                else:
                    raise ValueError('Invalid combination of table and operation: <{table}:{operation}>'.format(
                                                                                    table=table,
                                                                                    operation=operation))
            else:
                raise ValueError('Unkown operation request <{0}>, valid operations: {1}'.format(operation,
                                                                                                ['add', 'replace', 'delete']))

        self.request[msg.id] = msg
        return msg.id


    def label(self, id = None, operation = None, key_label=None, key_preference=None,
              ing_stats_enable=None, json=None):
        '''
            Constructs ModifyRequest with LabelTableEntry message and adds it to request queue.

            Args:
                id (int): mandatory argument for ModifyRequest
                operation (str): oneof add, replace, delete
                table (str): oneof ipv4, ipv6
                key_label (int)
                key_preference (int): ordering preference
                ttm_preference (int): tunnel table manager preference
                metric (int): tunnel table manager metric, used as a tiebreaker
                    between duplicate entries.
                json (str): whole message can be passed as json formatted sttring,
                    which needs to be enetered as valid json representation of
                    ModifyRequest.Request
        '''

        if json:
            msg = json_format.Parse(json, rib.ModifyRequest.Request())
        else:
            if not id:
                id = self.request_id()
            if operation in ['add', 'replace']:
                label_entry = rib.LabelTableEntry (
                                        entry_key = rib.LabelTableEntryKey(
                                                label = key_label,
                                                preference = key_preference
                                        ),
                                        ing_stats = rib.LabelTableIngrStats(
                                            enable = ing_stats_enable
                                        )
                                    )
                if operation == 'add':
                    msg = rib.ModifyRequest.Request(id=id,mpls_label_ADD = label_entry)
                else:
                    msg = rib.ModifyRequest.Request(id=id,mpls_label_REPLACE = label_entry)
            elif operation == 'delete':
                msg = rib.ModifyRequest.Request(
                                                id=id,
                                                mpls_label_DELETE = rib.LabelTableEntryKey(
                                                    label = key_label,
                                                    preference = key_preference
                                                )
                                            )
            else:
                raise ValueError('Unkown operation request <{0}>, valid operations: {1}'.format(operation, ['add', 'replace', 'delete']))

        self.request[msg.id] = msg
        return msg.id


    def next_hop_switch(self, id=None, endpoint=None, label=None,
                        nh_group_id=None, nhs_type=None, preference=None,
                        json=None):
        '''
            Constructs NextHopSwitch message.

            Args:
                id (int): mandatory argument for ModifyRequest
                endpoint (str): ipv4 or ipv6 address
                label (int): mpls label
                nh_group_id (int)
                nhs_type (str): oneof INVALID, Primary, Backup
                performance (int)
        '''

        if json:
            msg = json_format.Parse(json, rib.ModifyRequest.Request())
        else:
            if not id:
                id = self.request_id()
            msg = rib.ModifyRequest.Request(id=id,
                                                    NH_SWITCH=rib.NextHopSwitch(
                                                        endpoint=endpoint,
                                                        label=label,
                                                        nh_group_id=nh_group_id,
                                                        preference=preference,
                                                        type=nhs_type))
        self.request[id] = msg
        return msg.id


    def end_of_rib(self, id=None, table_id=None, json=None):
        '''
            Constructs EndOfRib message.


        '''

        if json:
            msg = json_format.Parse(json, rib.ModifyRequest.Request())
        else:
            if not id:
                id = self.request_id()
            msg = rib.ModifyRequest.Request(id=id,
                                                END_OF_RIB=rib.EndOfRib(id=table_id))
        self.request[id] = msg
        return msg.id


    def next_hop_group(self, request_id=None, group_id=None, weight=None, primary_ip=None,
              primary_labels=None, backup_ip=None, backup_labels=None, json=None):
        '''
            Constructs NextHopGroup message.
            NextHopGroup cannot be added to request as standalone message but instead
            has to appended to tunnel or label entry, therefore request_id with id
            of already existing request must be specified.

            Args:
                request_id (int): id of request which will be extended by this group.
                    If this is not specified, ValueError is raised.
                group_id (int): id within NHG
                weight (int)
                primary_ip (str): ipv4 or ipv6 address
                primary_labels (list of int)
                backup_ip (str): ipv4 or ipv6
                backup_labels (list of int)

        '''

        if not request_id:
            raise ValueError('request_id must be specified for NextHopGroup')

        if json:
            group = json_format.Parse(json, rib.NextHopGroup())
        else:
            if type(primary_labels) is not list and primary_labels:
                primary_labels = [int(x) for x in primary_labels.split(',')]
            if primary_ip or primary_labels:
                next_hop_primary = rib.NextHop(
                                        ip_address = primary_ip,
                                        pushed_label_stack = primary_labels)
            else:
                next_hop_primary = None

            if type(backup_labels) is not list and backup_labels:
                backup_labels = [int(x) for x in backup_labels.split(',')]
            if backup_ip or backup_labels:
                next_hop_backup = rib.NextHop(
                                        ip_address = backup_ip,
                                        pushed_label_stack = backup_labels)
            else:
                next_hop_backup = None

            group = rib.NextHopGroup(
                        id = group_id,
                        weight = weight,
                        primary = next_hop_primary,
                        backup = next_hop_backup)

        msg_type = self.request[request_id].WhichOneof('data')
        if msg_type == 'ipv4_tunnel_ADD':
            self.request[request_id].ipv4_tunnel_ADD.groups.extend([group])
        elif msg_type == 'ipv4_tunnel_REPLACE':
            self.request[request_id].ipv4_tunnel_REPLACE.groups.extend([group])
        elif msg_type == 'ipv6_tunnel_ADD':
            self.request[request_id].ipv6_tunnel_ADD.groups.extend([group])
        elif msg_type == 'ipv6_tunnel_REPLACE':
            self.request[request_id].ipv6_tunnel_REPLACE.groups.extend([group])
        elif msg_type == 'mpls_label_ADD':
            self.request[request_id].mpls_label_ADD.groups.extend([group])
        elif msg_type == 'mpls_label_REPLACE':
            self.request[request_id].mpls_label_REPLACE.groups.extend([group])
        return request_id






