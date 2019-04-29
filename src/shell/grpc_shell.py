

import click
import sys
import os
import time

from configparser import ConfigParser
import pickle
import logging
from logging.handlers import WatchedFileHandler

from click_shell import shell, make_click_shell
import click_completion

# put all supported grpc services here
import services.gnmi_service as gnmi
import services.rib_api_service as rib_api
import services.grpc_lib as grpc_lib

try:
    import gnureadline as readline
except ImportError:
    readline = None

logger = logging.getLogger()

_version = "0.0.1"
home = os.path.expanduser('~')
default_config_file = os.path.join(home,"grpc_shell.ini")
history_file = os.path.join(home,".grpc_shell.history")
default_delimiter = '/'
default_prompt = '(grpc-shell) > '
startup_config = None
teardown_config = None

@click.group(name='grpc_shell')
@click.pass_context
def grpc_shell(ctx):
    '''
        Entry point for grpc_shell for following services:

        |  gNMI
        |    Get
        |    Set
        |    Subscribe
        |    Capabilities

        |  RibApi
        |    GetVersion
        |    Modify
    '''
    pass

@grpc_shell.group(chain=True, name='show')
@click.pass_context
def show(ctx):
    pass

@grpc_shell.command(name='history')
@click.argument('lines', default=10)
def history(lines):
    history_file = os.path.join(home,".grpc_shell.history")
    if not os.path.isfile(history_file):
        click.secho('History file not found in {0}'.format(history_file), fg='red')
        return
    else:
        click.echo("")
        hist_length = readline.get_current_history_length()
        for x in range(hist_length, hist_length-lines, -1):
            click.secho(str(readline.get_history_item(x)))
        click.echo("")


@grpc_shell.command(name='listen')
def listen():
    """
        This will implement server which
        will listen for any commands sent to client
        on some port.
        For now, it only exists on KeyboardInterrupt
        exception.
    """
    reason = None
    try:
        while True:
            # ugly placeholder - time.sleep still listens for ctrl-c
            # and doesnt consume lot of cpu cycles
            # this will be replaced by server loop
            time.sleep(1000)
    except KeyboardInterrupt:
        reason = 'KeyboardInterrupt'
    click.secho('Block interrupted by {reason}'.format(reason=reason))


def exec_config_fc(exec_file=None):
    try:
        with open(exec_file, 'r') as f:
            commands = [cmd.strip() for cmd in f.readlines()]
            click.secho('\nGoing to execute {0} commands from {1}\n'.format(len(commands), f.name))
            main_shell.cmdqueue.extend(commands)
    except IOError as e:
        click.secho('Reading exec file {0} failed with error:\n{1}\n'.format(exec_file, e), fg='red')

@grpc_shell.command(name='exec_config')
@click.option('--exec_file', type=str)
def exec_config(exec_file):
    exec_config_fc(exec_file=exec_file)

def load_config_fc(ctx, config_file=default_config_file):
    if not os.path.isfile(config_file):
        click.secho('Default config {0} not found.\n'.format(config_file), fg='yellow')
        return
    try:
        defaults = ConfigParser()
        defaults.read(config_file)

        # for backward compatiblity check for both context and connect sessions
        if defaults.has_section('context') or defaults.has_section('connect'):
            context_default = dict()
            if defaults.has_section('context'):
                context_default['connect'] = dict(defaults.items('context'))
            elif defaults.has_section('connect'):
                context_default['connect'] = dict(defaults.items('connect'))
            ctx.default_map = context_default
            click.secho('Successfully loaded default session settings from {0}'.format(config_file), fg='green')

        if defaults.has_section('settings'):
            settings_defaults = dict(defaults.items('settings'))
            if 'default_delimiter' in settings_defaults:
                global default_delimiter
                default_delimiter = settings_defaults['default_delimiter']
            if 'startup_config' in settings_defaults:
                global startup_config
                startup_config = settings_defaults['startup_config']
        if defaults.has_section('environment'):
            environment = dict(defaults.items('environment'))
            for key in environment:
                if environment[key] == 'None':
                    try:
                        del os.environ[key]
                    except KeyError:
                        #no such setting in current environment, but thats ok
                        pass
                else:
                    os.environ[key] = environment[key]

        click.secho(('\nDefault config file {0} is automatically loaded at the beginning of each session.\n'
                     'To change this behaviour, remove the config or call grpc_shell with\n'
                     'custom config file like: grpc_shell <my_config_file_name>\n').format(config_file))
    except Exception as e:
        click.secho('Failed parsing config file at path {0} - {1}'.format(os.path.abspath(config_file) ,e), fg='red')
        raise

@grpc_shell.command(name='load_config')
@click.argument('config_file', default = 'grpc_shell.ini', type=click.Path(exists=True,readable=True))
@click.pass_context
def load_config(ctx, config_file):
    return load_config_fc(ctx, config_file=config_file)


@grpc_shell.group(invoke_without_command=True, name='gnmi_get')
@click.option('--name', default='default_get', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def gnmi_get(ctx, name, paging):
    '''
        gNMI.Get unary rpc - sends resquest consisting of paths to deserved data and
        returns all the data at once in GetRespone - one noticfication per one path
        requested. Since whole response must be srialized at remote device before
        sending, this rpc is not suitable for retrieving large sets of data.
    '''
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'gNMI.Get'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))

            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = gnmi.Get(stub=ctx.obj['gnmi_stub'],
                                                                        metadata=ctx.obj['context'].metadata,
                                                                        name=name,
                                                                        delimiter=default_delimiter)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            sys.exit()

@gnmi_get.command(name='request')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def request(ctx, paging):
    '''
        Displays request currently being built in clients.
    '''
    if paging:
        click.echo_via_pager(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].request))
    else:
        click.secho(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].request))

@gnmi_get.command(name='response')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def response(ctx, paging):
    '''
        Displays response from the last RPC call.
    '''
    if paging:
        click.echo_via_pager(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].response))
    else:
        click.secho(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].response))

@gnmi_get.command(name='error')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def error(ctx, paging):
    '''
        Displays error from last rpc call.
    '''
    if paging:
        click.echo_via_pager(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error))
    else:
        click.secho(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error))



@gnmi_get.command(name='prefix')
@click.argument('prefix', type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def prefix(ctx, prefix, delimiter):
    '''
        Sets prefix for GetRequest. If prefix was previously set it will be overwritten.
        Prefix applies to all paths in request.
        Requires xpath style strings with customizable delimiter. The query part of xpath
        cannot contain the symbol used for delimiter.
        eg: network-instances/network-instance[name=Base]
            configure/router[router-name=Base]
            configure_port[port-id=1/1/1]
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].prefix(prefix=prefix, delimiter=delimiter)

@gnmi_get.command(name='path')
@click.argument('path', type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def path(ctx, path, delimiter):
    '''
        Appends path to GetRequest. In case prefix is specified, only paths staring after last
        element can be specified.
        Requires xpath style strings with customizable delimiter. The query part of xpath
        cannot contain the symbol used for delimiter.
        eg: network-instances/network-instance[name=Base]
            configure/router[router-name=Base]
            configure_port[port-id=1/1/1]
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].path(path=path, delimiter=delimiter)

@gnmi_get.command(name='type')
@click.argument('type', type=str)
@click.pass_context
def type(ctx, type):
    '''
        Adds DataType to GetRequest - all|config|state|operational
    '''
    type = type.upper()
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].data_type(data_type=type)

@gnmi_get.command(name='models')
@click.option('--name', default=None, type=str)
@click.option('--organization', default=None, type=str)
@click.option('--version', default=None, type=str)
@click.pass_context
def models(ctx, name, organization, version):
    '''
        Appends ModelData to GetRequest
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].use_models(name=name,
                                                                            organization=organization,
                                                                            version=version)

@gnmi_get.command(name='encoding')
@click.argument('encoding', type=str)
@click.pass_context
def encoding(ctx, encoding):
    '''
        Adds Encoding to GetRequest.
        Default encoding is JSON.
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].set_encoding(encoding=encoding)

@gnmi_get.command(name='save')
@click.option('--output', default='default_get.data', type=click.File('wb'))
@click.option('--format', default='json', type=click.Choice(['json', 'dict', 'binary', 'text']))
@click.pass_context
def save(ctx, output, format):
    '''
        Saves current request to output file in given format.
        'json' jain compliant format, default values including unset fields are also preserved
        'dict' format is python dictionary serialized with pickle library
        'binary' format is protobuf raw data format
        'text' is str representation of protobuf data, THIS CANNOT BE PARSED BACK TO PROTOBUF MESSAGE
    '''
    if format == 'json':
        output.write(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_json())
    elif format == 'dict':
        pickle.dump(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_dict(),
                    output)
    elif format == 'binary':
        output.write(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_binary())
    elif format == 'text':
        output.write(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']]))


@gnmi_get.command(name='load')
@click.option('--input', default='default_get.data', type=click.File('r'))
@click.option('--format', default='json', type=click.Choice(['json', 'dict', 'binary', 'text']))
@click.pass_context
def load(ctx, input, format):
    '''
        Loads request from given file and transforms it to protobuf message
    '''
    if format == 'json':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_json(input.read())
    elif format == 'dict':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_dict(pickle.load(input))
    elif format == 'binary':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_binary(input.read())


@gnmi_get.command(name='execute')
@click.option('--process', default='blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Blocking process waits for rpc to finish. non-blocking returns '
                    'immediately and progress or response can be monitored by response '
                    'subcommand for given RPC.'))
@click.option('--timeout', default=300, type=int,
              help=('number of seconds to wait in case of blocking call, '
                    'value -1 means no timeout'))
@click.pass_context
def execute(ctx, process, timeout):
    '''
        Executes rpc.
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].execute()

    if process == 'blocking':
        if timeout == -1:
            timeout = None
        try:
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.join(timeout)
            if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.is_alive():
                click.secho('\nMax wait limit {0}s exceeded\n'.format(timeout), fg='red')
            else:
                err = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error
                if err:
                    click.secho('Rpc finished with error:\n{0}'.format(err), fg='red')
                else:
                    click.secho('Rpc finished, call \'gnmi_get {0} response\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
        except Exception as e:
            click.secho('\nError while executing rpc: {0}\n'.format(e))


@gnmi_get.command(name='clear')
@click.pass_context
def clear(ctx):
    '''
        Clears request, response and error fields.
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].clear()


@gnmi_get.command(name='destroy')
@click.pass_context
def destroy(ctx):
    '''
        Removes RPC object from rpc manager.
        Rpc with same name and new params can be created afterwards.
    '''
    try:
        ctx.obj['manager'].destroy(rpc_type=ctx.obj['RPC_TYPE'], name=ctx.obj['RPC_NAME'])
        click.secho('Rpc with type {0} and name {1} removed from manager'.format(
                                                                            ctx.obj['RPC_TYPE'],
                                                                            ctx.obj['RPC_NAME']
                                                                            ),
                                                                            fg='green'
                                                                        )
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')
        raise


@grpc_shell.group(invoke_without_command=True, name='gnmi_set')
@click.option('--name', default='default_set', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def gnmi_set(ctx, name, paging):
    '''
        gNMI.Set unary rpc. All submitted configuration is
        sent to to remote device and applied in one transaction.
    '''
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'gNMI.Set'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))

            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = gnmi.Set(stub=ctx.obj['gnmi_stub'],
                                                                        metadata=ctx.obj['context'].metadata,
                                                                        name=name,
                                                                        delimiter=default_delimiter)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            sys.exit()

@gnmi_set.command(name='prefix')
@click.argument('prefix', default=None, type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def prefix(ctx, prefix, delimiter):
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].prefix(prefix=prefix,
                                                                                 delimiter=delimiter)

@gnmi_set.command(name='update')
@click.argument('path', default=None, type=str)
@click.option('--values', default=None, multiple=True, type=(str, str),
              help='Tuples of element name and element value')
@click.option('--types', default=None, multiple=True, type=str,
              help='List of element types')
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def update(ctx, path, values, types, delimiter):
    '''
        Performs merge operation. Due to how json types maps to yang types, in some cases also types
        for given values must be provided. Client by defualt does best effort to figure out types.
        Mapping and names of types are decribed in RFC 7951.
        https://tools.ietf.org/html/rfc7951
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].update(operation='update',
                                                                             path=path,
                                                                             values=values,
                                                                             types=types,
                                                                             delimiter=delimiter)

@gnmi_set.command(name='replace')
@click.argument('path', default=None, type=str)
@click.option('--values', default=None, multiple=True, type=(str, str),
              help='Tuples of element name and element value')
@click.option('--types', default=None, multiple=True, type=str,
              help='Optional element type')
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def replace(ctx, path, values, types, delimiter):
    '''
        Deletes everything under context specified by path and then performs updates provided in values.
        Due to how json types maps to yang types, in some cases also types
        for given values must be provided. Client by defualt does best effort to figure out types.
        Mapping and names of types are decribed in RFC 7951.
        https://tools.ietf.org/html/rfc7951
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].update(operation='replace',
                                                                             path=path,
                                                                             values=values,
                                                                             types=types,
                                                                             delimiter=delimiter)

@gnmi_set.command(name='delete')
@click.argument('path', default=None, type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def delete(ctx, path, delimiter):
    '''
        Deletes everything under context specified by path.
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].update(operation='delete',
                                                                             path=path,
                                                                             delimiter=delimiter)

@gnmi_set.command(name='execute')
@click.option('--process', default='blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Run RPC. blocking process waits for rpc to finish. non-blocking returns '
                    'immediately.'))
@click.option('--timeout', default=300, type=int,
              help=('number of seconds to wait in case of blocking call, '
                    'value -1 means no timeout'))
@click.pass_context
def execute(ctx, process, timeout):
    '''
        Executes rpc
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].execute()

    if process == 'blocking':
        if timeout == -1:
            timeout = None
        try:
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.join(timeout)
            if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.is_alive():
                click.secho('\nMax wait limit {0}s exceeded\n'.format(timeout), fg='red')
            else:
                err = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error
                if err:
                    click.secho('Rpc finished with error:\n{0}'.format(err), fg='red')
                else:
                    click.secho('Rpc finished, call \'gnmi_set --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
        except Exception as e:
            click.secho('\nError while executing rpc: {0}\n'.format(e))

@gnmi_set.command(name='clear')
@click.pass_context
def clear(ctx):
    '''
        Clears request, response and error fields.
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].clear()

@gnmi_set.command(name='save')
@click.option('--output', default='default_set.data', type=click.File('wb'))
@click.option('--format', default='json', type=click.Choice(['json', 'dict', 'binary', 'text']))
@click.pass_context
def save(ctx, output, format):
    '''
        Saves current request to output file in given format.
        'json' jain compliant format, default values including unset fields are also preserved
        'dict' format is python dictionary serialized with pickle library
        'binary' format is protobuf raw data format
        'text' is str representation of protobuf data, THIS CANNOT BE PARSED BACK TO PROTOBUF MESSAGE
    '''
    if format == 'json':
        output.write(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_json())
    elif format == 'dict':
        pickle.dump(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_dict(),
                    output)
    elif format == 'binary':
        output.write(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_binary())
    elif format == 'text':
        output.write(str(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']]))


@gnmi_set.command(name='load')
@click.option('--input', default='default_set.data', type=click.File('r'))
@click.option('--format', default='json', type=click.Choice(['json', 'dict', 'binary']))
@click.pass_context
def load(ctx, input, format):
    '''
        Loads request from
    '''
    if format == 'json':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_json(input.read())
    elif format == 'dict':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_dict(pickle.load(input))
    elif format == 'binary':
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_binary(input.read())

@gnmi_set.command(name='destroy')
@click.pass_context
def destroy(ctx):
    '''
        Removes RPC object from rpc manager.
        Rpc with same name and new params can be created afterwards.
    '''
    try:
        ctx.obj['manager'].destroy(rpc_type=ctx.obj['RPC_TYPE'], name=ctx.obj['RPC_NAME'])
        click.secho('Rpc with type {0} and name {1} removed from manager'.format(
                                                                            ctx.obj['RPC_TYPE'],
                                                                            ctx.obj['RPC_NAME']
                                                                            ),
                                                                            fg='green'
                                                                        )
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')

@grpc_shell.group(invoke_without_command=True, name='gnmi_capabilities')
@click.option('--name', default='default_capabilities', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def gnmi_capabilities(ctx, name, paging):
    '''
        gNMI.Capabilities unary rpc 
    '''
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'gNMI.Capabilities'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))

            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = gnmi.Capabilities(stub=ctx.obj['gnmi_stub'],
                                                                        metadata=ctx.obj['context'].metadata,
                                                                        name=name)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            raise
            sys.exit()


@gnmi_capabilities.command(name='execute')
@click.option('--process', default='blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Run RPC. blocking process waits for rpc to finish. non-blocking returns '
                    'immediately.'))
@click.option('--timeout', default=300, type=int,
              help=('number of seconds to wait in case of blocking call, '
                    'value -1 means no timeout'))
@click.pass_context
def execute(ctx, process, timeout):
    '''
        Executes rpc
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].execute()

    if process == 'blocking':
        if timeout == -1:
            timeout = None
        try:
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.join(timeout)
            if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.is_alive():
                click.secho('\nMax wait limit {0}s exceeded\n'.format(timeout), fg='red')
            else:
                err = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error
                if err:
                    click.secho('Rpc finished with error:\n{0}'.format(err), fg='red')
                else:
                    click.secho('Rpc finished, call \'gnmi_capabilities --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
        except Exception as e:
            click.secho('\nError while executing rpc: {0}\n'.format(e))


@grpc_shell.group(invoke_without_command=True, name='gnmi_subscribe')
@click.option('--name', default='default_subscribe', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.option('--mode', default='STREAM', type=click.Choice(['STREAM','ONCE','POLL']))
@click.option('--qos', default=None, type=int)
@click.option('--prefix', default=None, type=str)
@click.option('--allow_aggregation', default=False, type=bool)
@click.option('--use_aliases', default=False, type=bool)
@click.pass_context
def gnmi_subscribe(ctx, name, paging, mode, qos, prefix, allow_aggregation, use_aliases):
    '''
        Entry point for subscribe rpc.
    '''
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'gNMI.Subscribe'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = gnmi.Subscribe(stub=ctx.obj['gnmi_stub'],
                                                                         metadata=ctx.obj['context'].metadata,
                                                                         server_addr=ctx.obj['context'].ip,
                                                                         server_port=ctx.obj['context'].port,
                                                                         name=name,
                                                                         mode=mode,
                                                                         prefix=prefix,
                                                                         delimiter=default_delimiter,
                                                                         qos=qos,
                                                                         allow_aggregation=allow_aggregation,
                                                                         use_aliases=use_aliases)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            sys.exit()

@gnmi_subscribe.command(name='prefix')
@click.argument('prefix', type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.pass_context
def prefix(ctx, prefix, delimiter):
    '''
        Sets prefix for GetRequest. If prefix was previously set it will be overwritten.
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].prefix(prefix=prefix, delimiter=delimiter)

@gnmi_subscribe.command(name='subscribe')
@click.argument('path', type=str)
@click.option('--delimiter', type=str, default=None, help='delimiter to separate path elements')
@click.option('--trigger', type=click.Choice(['SAMPLE', 'ON_CHANGE', 'TARGET_DEFINED']))
@click.option('--interval', type=int, help='Sampling interval in seconds')
@click.option('--suppress_redundant', default=False, type=bool)
@click.option('--heartbeat_interval', default=None, type=int)
@click.pass_context
def subscribe(ctx, path, delimiter, trigger, interval, suppress_redundant, heartbeat_interval):
    '''
        Fills subscribe RPC with given data.
        First positional argument is path you wish to subscribe to.
    '''
    delimiter = str(delimiter) if delimiter else default_delimiter
    if interval:
        interval = interval*10**9
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].subscription(path=path,
                                                                                   delimiter=delimiter,
                                                                                   trigger=trigger,
                                                                                   interval=interval,
                                                                                   suppress_redundant=suppress_redundant,
                                                                                   heartbeat_interval=heartbeat_interval)


@gnmi_subscribe.command(name='log')
@click.option('--file_path', default=None, type=str)
@click.option('--data_format', default='json', type=str)
@click.pass_context
def log(ctx, file_path, data_format):
    '''
        Redirects data logged by telemetry to different log file
    '''
    if not file_path:
        file_path = "{0}.log".format(ctx.obj['RPC_NAME'])

    try:
        if data_format == 'json':
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].target = file_path
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].response_processor = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].json_response_processor
        else:
            click.secho('\nOnly json format is currently supported\n', fg='red')
    except Exception as e:
        click.secho('\nError while chainging response_processor: {0}\n'.format(e), fg='red')

@gnmi_subscribe.command(name='forward_stream')
@click.option('--ip', default=None, type=str)
@click.option('--port', default=None, type=int)
@click.option('--protocol', default='udp', type=str)
@click.option('--formatting', default='json', type=str)
@click.pass_context
def forward_stream(ctx, ip, port, protocol, formatting):
    '''
        Forwards notifications over one of chosen protocols
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].stream(ip=ip,
                                                                             port=port,
                                                                             protocol=protocol,
                                                                             formatting=formatting)
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].response_processor = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].stream_response_processor
    click.secho('Notifications will be streamed to {0} over {1} with {2} format'.format(
                                                                                    ip + ":" + str(port),
                                                                                    protocol,
                                                                                    formatting
                                                                                ),
                                                                                fg = 'green')

@gnmi_subscribe.command(name='execute')
@click.option('--process', default='non-blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Run RPC. blocking process waits for rpc to finish. non-blocking returns '
                    'immediately.'))
@click.option('--timeout', default=300, type=int,
              help=('number of seconds to wait in case of blocking call.'))
@click.pass_context
def execute(ctx, process, timeout):
    '''
        Executes rpc
    '''
    try:
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].execute()
        if process == 'blocking':
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.join(timeout)
            if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.is_alive():
                click.secho('\nMax wait limit {0}s exceeded\n'.format(timeout), fg='red')
            else:
                err = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error
                if err:
                    click.secho('Rpc finished with error:\n{0}'.format(err), fg='red')
                else:
                    click.secho('Rpc finished, call \'gnmi_subscribe --name {0} response\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
    except Exception as e:
        click.secho('\nError while executing rpc: {0}\n'.format(e))

@gnmi_subscribe.command(name='poll')
@click.pass_context
def poll(ctx):
    '''
        Triggers retrieval of data from remote side.
    '''
    try:
        if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker:
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].poll()
        else:
            click.secho('Poll request requires running subscription')
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')

@gnmi_subscribe.command(name='cancel')
@click.pass_context
def cancel(ctx):
    '''
        Cancels the rpc on remote side.
    '''
    try:
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].cancel()
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')

@gnmi_subscribe.command(name='clear')
@click.pass_context
def clear(ctx):
    '''
        Removes subscriptions from this rpc.
    '''
    try:
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].clear()
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')

@gnmi_subscribe.command(name='destroy')
@click.pass_context
def destroy(ctx):
    '''
        Removes RPC object from rpc manager.
        Rpc with same name and new params can be created afterwards.
    '''
    try:
        ctx.obj['manager'].destroy(rpc_type=ctx.obj['RPC_TYPE'], name=ctx.obj['RPC_NAME'])
        click.secho('Rpc with type {0} and name {1} removed from manager'.format(
                                                                            ctx.obj['RPC_TYPE'],
                                                                            ctx.obj['RPC_NAME']
                                                                            ),
                                                                            fg='green'
                                                                        )
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')

@grpc_shell.group(invoke_without_command=True, name='rib_getversion')
@click.option('--name', default='default_getversion', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def rib_getversion(ctx, name, paging):
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'RibApi.GetVersion'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))

            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = rib_api.GetVersion(stub=ctx.obj['rib_fib_stub'],
                                                                            metadata=ctx.obj['context'].metadata,
                                                                            name=name)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            sys.exit()

@rib_getversion.command(name='execute')
@click.option('--process', default='blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Run RPC. blocking process waits for rpc to finish. non-blocking returns '
                    'immediately and progress or response can be monitored by response '
                    'subcommand for given RPC.'))
@click.option('--timeout', default=300, type=int,
              help=('number of seconds to wait in case of blocking call, '
                    'value -1 means no timeout'))
@click.pass_context
def execute(ctx, process, timeout):
    '''
        Executes rpc
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].execute()

    if process == 'blocking':
        if timeout == -1:
            timeout = None
        try:
            ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.join(timeout)
            if ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].worker.is_alive():
                click.secho('\nMax wait limit {0}s exceeded\n'.format(timeout), fg='red')
            else:
                err = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].error
                if err:
                    click.secho('Rpc finished with error:\n{0}'.format(err), fg='red')
                else:
                    click.secho('Rpc finished, call \'gnmi_get --name {0} response\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
        except Exception as e:
            click.secho('\nError while executing rpc: {0}\n'.format(e))

@grpc_shell.group(invoke_without_command=True, name='rib_modify')
@click.option('--name', default='default_modify', type=str, help='RPCs given name - used for managing RPCs in this client')
@click.option('--paging', is_flag=True, help='Use pager inherited from shell in case there is long text to display.')
@click.pass_context
def rib_modify(ctx,name, paging):
    '''
        RibApi.Modify
    '''
    if ctx.invoked_subcommand != 'help':
        try:
            rpc_type = 'RibApi.Modify'
            if name in ctx.obj['manager'].rpcs[rpc_type]:
                if ctx.invoked_subcommand is None:
                    if paging:
                        click.echo_via_pager(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))
                    else:
                        click.echo(ctx.obj['manager'].get_rpc(type=rpc_type, name=name))

            else:
                click.secho('Rpc with name \'{name}\' doesnt exists, adding one to rpc manager'.format(name=name), fg='yellow')
                ctx.obj['manager'].rpcs[rpc_type][name] = rib_api.Modify(stub=ctx.obj['rib_fib_stub'],
                                                                         metadata=ctx.obj['context'].metadata,
                                                                         name=name)
            ctx.obj['RPC_NAME'] = name
            ctx.obj['RPC_TYPE'] = rpc_type
        except KeyError as e:
            click.secho('\nYou have to create at least one connection before creating RPCs\n', fg='red')
            sys.exit()

@rib_modify.command(name='route')
@click.argument('operation')
@click.argument('table')
@click.option('--id', default=None, type=int, help='request id')
@click.option('--key_prefix', default=None, help='IP prefix and prefix length in CIDR')
@click.option('--key_preference', default=None, type=int, help=('Key; this is ordering preference for '
                                                 'multiple routes with same prefix for '
                                                 'ordering within the RIB-API module'))
@click.option('--rtm_preference', default=None, type=int)
@click.option('--metric', default=None, type=int)
@click.option('--tunnel_next_hop', default=None)
@click.pass_context
def route(ctx, operation, table, id, key_prefix, key_preference, rtm_preference, metric, tunnel_next_hop):
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].route(operation=operation,
                                                                            table=table,
                                                                            id=id,
                                                                            key_prefix=key_prefix,
                                                                            key_preference=key_preference,
                                                                            rtm_preference=rtm_preference,
                                                                            metric=metric,
                                                                            tunnel_next_hop=tunnel_next_hop
                                                                        )


@rib_modify.command(name='tunnel')
@click.argument('operation')
@click.argument('table')
@click.option('--id', default=None, type=int, help='request id')
@click.option('--key_endpoint', default=None, help='IP prefix and prefix length in CIDR')
@click.option('--key_preference', default=None, type=int, help=('Key; this is ordering preference for '
                                                 'multiple routes with same prefix for '
                                                 'ordering within the RIB-API module'))
@click.option('--ttm_preference', default=None, type=int)
@click.option('--metric', default=None, type=int)
@click.pass_context
def tunnel(ctx, operation, table, id, key_endpoint, key_preference, ttm_preference, metric):
    ctx.obj['last_req'] = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].tunnel(
                                                                            operation=operation,
                                                                            table=table,
                                                                            id=id,
                                                                            key_endpoint=key_endpoint,
                                                                            key_preference=key_preference,
                                                                            ttm_preference=ttm_preference,
                                                                            metric=metric
                                                                        )

@rib_modify.command(name='label')
@click.argument('operation')
@click.option('--id', default=None, type=int, help='request id')
@click.option('--key_label', default=None, type=int)
@click.option('--key_preference', default=None, type=int)
@click.option('--ing_stats_enable', default=None, type=int)
@click.option('--type', default=None,type=str)
@click.pass_context
def label(ctx, operation, id, key_label, key_preference, ing_stats_enable, type):
    ctx.obj['last_req'] = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].label(
                                                                            operation=operation,
                                                                            id=id,
                                                                            key_label=key_label,
                                                                            key_preference=key_preference,
                                                                            ing_stats_enable=ing_stats_enable,
                                                                            type=type
                                                                        )

@rib_modify.command(name='next_hop_group')
@click.option('--request_id', default = None, type=int)
@click.option('--group_id', default = None, type=int)
@click.option('--weight', default = None, type=int)
@click.option('--primary_ip', default = None, type=str)
@click.option('--primary_labels', default = None, type=str)
@click.option('--backup_ip', default = None, type=str)
@click.option('--backup_labels', default = None, type=str)
@click.pass_context
def next_hop_group(ctx, request_id, group_id, weight, primary_ip, primary_labels, backup_ip, backup_labels):
    if 'last_req' not in ctx.obj:
        click.secho('At least one request supporting next-hop-group must be created', fg='red')
        sys.exit()
    if not request_id:
        request_id = ctx.obj['last_req']
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].next_hop_group(
                                                                        request_id=request_id,
                                                                        group_id=group_id,
                                                                        weight=weight,
                                                                        primary_ip=primary_ip,
                                                                        primary_labels=primary_labels,
                                                                        backup_ip=backup_ip,
                                                                        backup_labels=backup_labels
                                                                    )


@rib_modify.command(name='next_hop_switch')
@click.option('--id', default=None, type=int, help='request id')
@click.option('--endpoint', default=None, type=str, help='Ipv4 or Ipv6 address')
@click.option('--label', default=None, type=int, help='mpls label')
@click.option('--preference', default=None, type=int, help='ordering preference for multiple entries with same key')
@click.option('--nh_group_id', default=None, type=int, help='Index for nexthop group')
@click.option('--type', default=None, help='Index for nexthop group', type=click.Choice(['INVALID', 'Primary', 'Backup']))
@click.pass_context
def next_hop_switch(ctx, id, endpoint, label, nh_group_id, type, preference):
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].next_hop_switch(
                                                                                        id=id,
                                                                                        endpoint=endpoint,
                                                                                        label=label,
                                                                                        nh_group_id=nh_group_id,
                                                                                        preference=preference,
                                                                                        type=type
                                                                                     )

@rib_modify.command(name='end_of_rib')
@click.option('--id', default=None, type=int, help='request id')
@click.option('--table_id', default=None, help='enum TableId specified in EndOfRib',
              type=click.Choice(['INVALID',
                                 'IPv4RouteTable',
                                 'IPv6RouteTable',
                                 'IPv4TunnelTable',
                                 'IPv6TunnelTable',
                                 'MplsLabelTable']))
@click.pass_context
def end_of_rib(ctx, id, table_id):
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].end_of_rib(id=id,
                                                                                 table_id=table_id
                                                                                )


@rib_modify.command(name='execute')
@click.option('--process', default='non-blocking', type=click.Choice(['blocking', 'non-blocking']),
              help=('Run RPC. blocking process waits for rpc to finish. non-blocking returns '
                    'immediately.'))
@click.option('--timeout', default=300, type=int, help='number of seconds to wait in case of blocking call')
@click.option('--paging', is_flag=True)
@click.pass_context
def execute(ctx, process, timeout, paging):
    '''
        Executes rpc.
        This call is by default non-blocking. When this is overriden by
        specifing --process blocking option, the prompt is blocked
        for time specified by timeout parameter. Error is raised if
        timeout or RPC runtime error occurs.
    '''
    rpc = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']]
    rpc.execute()

    if process == 'blocking':
        try:
            rpc.wait(timeout=timeout)
            if rpc.work_queue.unfinished_tasks:
                click.secho('Not all rpc requests were processed, \'rib_modify --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='red')
            else:
                click.secho('Rpc finished, call \'rib_modify --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
        except Exception as e:
            click.secho('\nError while executing rpc: {0}\n'.format(e), fg='red')

@rib_modify.command(name='block')
@click.option('--timeout', default=30, type=int, help='number of seconds to wait in case of blocking call')
@click.pass_context
def block(ctx, timeout):
    '''
        Blocks until all requests are processed or timeout occurs.
    
    '''
    try:
        rpc = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']]
        rpc.wait(timeout=timeout)
        if rpc.work_queue.unfinished_tasks:
            click.secho('Not all rpc requests were processed, \'rib_modify --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='red')
        else:
            click.secho('Rpc finished, call \'rib_modify --name {0}\' to show result'.format(ctx.obj['RPC_NAME']), fg='green')
    except Exception as e:
        click.secho('\nError while executing rpc: {0}\n'.format(e), fg='red')

@rib_modify.command(name='cancel')
@click.pass_context
def cancel(ctx):
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].cancel()

@rib_modify.command(name='clear')
@click.pass_context
def clear(ctx):
    '''
        Clears request, response and error fields.
    '''
    ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].clear()

@rib_modify.command(name='destroy')
@click.pass_context
def destroy(ctx):
    '''
        Removes RPC object from rpc manager.
        Rpc with same name and new params can be created afterwards.
    '''
    try:
        ctx.obj['manager'].destroy(rpc_type=ctx.obj['RPC_TYPE'], name=ctx.obj['RPC_NAME'])
        click.secho('Rpc with type {0} and name {1} removed from manager'.format(
                                                                            ctx.obj['RPC_TYPE'],
                                                                            ctx.obj['RPC_NAME']
                                                                            ),
                                                                            fg='green'
                                                                        )
    except Exception as e:
        click.secho('\n{0}\n'.format(e), fg='red')
        raise


@rib_modify.command(name='to_json')
@click.pass_context
def to_json(ctx):
    '''
        Prints currently loaded request messages.
    '''
    click.secho(ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].get_requests())

@rib_modify.command(name='save_json_file')
@click.option('--json_file', type=click.File('wb'))
@click.pass_context
def save_json_file(ctx, json_file):
    '''
        Saves file with JSON object,
        consisting of all request messages
        currently loaded in this RPC. 
    '''
    try:
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_json(file_path=json_file.name)
        click.secho('Saved message to json file {0}'.format(json_file.name), fg='green')
    except:
        click.secho('Exception occured, failed to save json file {0}'.format(json_file.name), fg='red')
        raise

@rib_modify.command(name='save_binary_file')
@click.option('--json_file', type=click.File('r'))
@click.pass_context
def load_json_file(ctx, json_file):
    '''
        Loads file with JSON object, consisting of request messages.
        
    '''
    try:
        count = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_json(file_path=json_file.name)
        click.secho('Loaded json file {0} with {1} requests into {2}'.format(
                                                                        json_file.name,
                                                                        count,
                                                                        ctx.obj['RPC_NAME']), fg='green')
    except:
        click.secho('Exception occured, failed to load json file {0}'.format(json_file.name), fg='red')
        raise

@rib_modify.command(name='save_binary_file')
@click.option('--binary_file', type=click.File('wb'))
@click.pass_context
def save_binary_file(ctx, binary_file):
    '''
        Saves file with protobuf binary object,
        consisting of all request messages
        currently loaded in this RPC. 
    '''
    try:
        ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].to_binary(file_path=binary_file.name)
        click.secho('Saved message to binary file {0}'.format(binary_file.name), fg='green')
    except:
        click.secho('Exception occured, failed to save binary file {0}'.format(binary_file.name), fg='red')
        raise

@rib_modify.command(name='load_binary_file')
@click.option('--binary_file', type=click.File('r'))
@click.pass_context
def load_binary_file(ctx, binary_file):
    '''
        Loads file with protobuf binary object, consisting of request messages.
        
    '''
    try:
        count = ctx.obj['manager'].rpcs[ctx.obj['RPC_TYPE']][ctx.obj['RPC_NAME']].from_json(file_path=binary_file.name)
        click.secho('Loaded binary file {0} with {1} requests into {2}'.format(
                                                                        binary_file.name,
                                                                        count,
                                                                        ctx.obj['RPC_NAME']), fg='green')
    except:
        click.secho('Exception occured, failed to load binary file {0}'.format(binary_file.name), fg='red')
        raise


@grpc_shell.command(name='edit_config')
@click.argument('config_file', type=click.Path())
def edit_config(config_file):
    if config_file:
        click.edit(filename=config_file)


@grpc_shell.command(name='connect')
@click.option('--ip', type=str, help='IPv4 or IPv6 address of grpc server')
@click.option('--port', type=str, help='application port of grpc server')
@click.option('--username', type=str)
@click.option('--password', prompt=True, hide_input=True)
@click.option('--auth_type', type=click.Choice(['mutual', 'server']), help='TLS authorization type')
@click.option('--root_cert', type=str, help='certification authority file')
@click.option('--cert', type=str, help='client certificate')
@click.option('--key', type=str, help='client private key')
@click.option('--skip_connection', is_flag=True, help='Client will just create stubs during connect command and wont ask remote device for service versions.')
@click.option('--transport', type=click.Choice(['secure', 'unsecure']), help='specify this flag in case you dont want to use TLS secured connections')
@click.option('--compression', type=click.Choice(['deflate', 'none', 'gzip']), help='compression algorithm advertised by client')
@click.pass_context
def connect(ctx, ip, port, username, password, auth_type, root_cert, cert, key, skip_connection, transport, compression):
    '''
        Stub is context object used to manage grpc connections
    '''
    try:
        ctx.obj['context'] =  grpc_lib.Channel(ip=ip, port=port, username=username,
                                          password=password, auth_type=auth_type,
                                          root_cert=root_cert, cert=cert, key=key,
                                          transport=transport, compression=compression)
    except Exception as e:
        click.secho('Creating channel failed: {0}'.format(e),  fg='red')
        return
    else:
        click.secho('Successfully created channel', fg = 'green')

    try:
        ctx.obj['gnmi_stub'] = gnmi.create_stub(channel=ctx.obj['context'].channel)
    except Exception as e:
        click.secho('Creating gNMI stub failed: {0}'.format(e), fg='red')
        ctx.obj['gnmi_stub'] = None

    try:
        ctx.obj['rib_fib_stub'] = rib_api.create_stub(service='RibApi', channel=ctx.obj['context'].channel)
    except Exception as e:
        click.secho('Creating RibApi stub failed: {0}'.format(e), fg='red')
        ctx.obj['rib_fib_stub'] = None

    # add option to skip service checks for users
    if not skip_connection:
        gnmi_rpc = gnmi.Capabilities(stub=ctx.obj['gnmi_stub'],
                                    metadata=ctx.obj['context'].metadata,
                                    name='initial connect')
        gnmi_rpc.execute()
        gnmi_rpc.worker.join(timeout=60)
        if gnmi_rpc.error:
            click.secho('Retrieving gNMI from remote device failed with error:\n{0}'.format(gnmi_rpc.error.details()), fg='red')
            ctx.obj['gnmi_version'] = None
        else:
            click.secho('gNMI service on remote device running with version: {0}'.format(gnmi_rpc.gNMI_version), fg='green')
            ctx.obj['gnmi_version'] = gnmi_rpc.gNMI_version

        try:
            gnmi_rpc.cancel()
        except:
            pass

        rib_rpc = rib_api.GetVersion(stub=ctx.obj['rib_fib_stub'],
                                     metadata=ctx.obj['context'].metadata,
                                     name='initial connect')
        rib_rpc.execute()
        rib_rpc.worker.join(timeout=60)
        if rib_rpc.error:
            click.secho('Retrieving RibApi version from remote device failed with error:\n{0}'.format(rib_rpc.error.details()), fg='red')
            ctx.obj['rib_version'] = None
        else:
            click.secho('RibApi service on remote device running with version: {0}'.format(rib_rpc.api_version), fg='green')
            ctx.obj['rib_version'] = rib_rpc.api_version

        try:
            rib_rpc.cancel()
        except:
            pass
    rpc_types = ['gNMI.Get', 'gNMI.Set', 'gNMI.Subscribe', 'gNMI.Capabilities', 'RibApi.Modify', 'RibApi.GetVersion']
    ctx.obj['manager'] = grpc_lib.RpcManager(rpc_types=rpc_types)


@show.command(name='context')
@click.pass_context
def context(ctx):
    try:
        click.echo(ctx.obj['context'])
    except KeyError:
        click.secho("No context found, use 'connect' command to create one", fg='red')


@show.command()
@click.pass_context
def manager(ctx):
    try:
        click.echo(ctx.obj['manager'])
    except KeyError:
        click.secho("No manager found, use 'connect' command to create one", fg='red')


@grpc_shell.command(name='set_prompt')
@click.argument('prompt', type=str)
def set_prompt(prompt):
    main_shell.prompt = prompt


@grpc_shell.command(name='clear')
def clear():
    click.clear()


@grpc_shell.command(name='set_log')
@click.option('--target', default='std', type=str)
def set_log(target):
    set_logger(target=target)
    click.secho('Changed target of logger to {0}'.format(target))


def set_logger(target='std'):
    global logger
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('\n%(asctime)s - %(name)s - %(levelname)s - \n%(message)s\n')
    if target == 'std':
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = WatchedFileHandler(target)
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def main(args=None):
    global main_shell
    set_logger()

    click_completion.init()
    ctx = click.Context(grpc_shell)
    try:
        load_config_fc(ctx, sys.argv[1])
    except IndexError:
        load_config_fc(ctx)
    ctx.obj = dict()
    main_shell = make_click_shell(ctx, prompt=default_prompt, intro='Starting grpc shell', hist_file=os.path.join(home,'.grpc_shell.history'))
    if startup_config:
        exec_config_fc(startup_config)
    main_shell.cmdloop()



if __name__ == '__main__':
    main()
