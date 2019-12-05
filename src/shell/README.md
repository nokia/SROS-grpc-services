
# grpc_shell

grpc_shell is simple cli tool to send gNMI and RibApi RPCs. Both services run on top of [gRPC](https://grpc.io/).
Grpc can provide secure channel via TLS with both mutual
and server side authentication, or unsecure channel - in that case all messages are
transported in plain-text, including username and password.

<!-- MarkdownTOC -->

  * [Basic config](#basic-config)
    + [Connection](#connection)
    + [History](#history)
    + [Settings](#settings)
    + [Environment](#environment)
  * [Exec files](#exec-files)
  * [gNMI service](#gnmi-service)
    + [Configuration mode limitations](#configuration-mode-limitations)
    + [gNMI Set RPC](#gnmi-set-rpc)
      - [Examples](#examples)
    + [gNMI Get RPC](#gnmi-get-rpc)
      - [Examples](#examples-1)
    + [gNMI Subscribe RPC](#gnmi-subscribe-rpc)
      - [Examples](#examples-2)
  * [RibApi Service](#ribapi-service)
    + [Configuration mode limitations](#configuration-mode-limitations-1)
    + [RibApi Modify RPC](#ribapi-modify-rpc)
      - [Examples](#examples-3)
  * [CertificateManagement service](#certificatemanagement-service)
      - [Examples](#examples-4)
        * [Install RPC with CSR from target](#install-rpc-with-csr-from-target)
        * [Rotate RPC with CSR from target](#rotate-rpc-with-csr-from-target)
        * [Locally created CSR](#locally-created-csr)

<!-- /MarkdownTOC -->


## Basic config
The tool is able to work with basic config file which can contain information about desired connection, some basic settings and enviroment variables specified in [environment variables doc](https://github.com/grpc/grpc/blob/master/doc/environment_variables.md). By default the tool looks for grpc_shell.ini in current users home directory. This can be overriden by specifing path to config file on tool startup:
```
grpc_shell /path/to/my/config.ini
```

### Connection
Example of INI file for unsecure connection:
```
[context]
ip: 192.168.90.103
port: 57400
username: admin
transport: unsecure
compression: deflate
```

And for secure connection:
```
[context]
ip: 192.168.90.103
port: 57400
username: admin
root_cert: CAcert_l1.pem
cert: cert_l1.pem
key: servkey_l1.pem
transport: secure
auth_type: mutual
compression: deflate
```

All of these paramaters can be overriden by options in connect command during interactive session.

### History

Tool also creates .grpc_shell.history in users home directory, so reverse-i-search is available and you can call history command within the tool to show last invoked commands.

### Settings

Some users might prefer certain options or perform certain actions everytime they start the client. These can be specified in settings portion of INI file. Currently supported settings are only default_delimiter and startup_config.

```
[settings]
default_delimiter: _
startup_config: /home/vacica/grpc_shell.cfg
```

### Environment

Grpc library accepts some of the runtime settings only in form of [environment variables](https://github.com/grpc/grpc/blob/master/doc/environment_variables.md). You can modify any of these in **environment** part of INI file. Python defualt behaviour is that it copies
environment from hosting system, you can check your current environment by executing this line in your system shell: *python -c "import os;print(os.environ)"*. For completely removing some variable from env you can specify its value to None in INI file.

```
[environment]
http_proxy: None
https_proxy: None
GRPC_SSL_CIPHER_SUITES: AES128
```

## Exec files

Any of the commands documented below can be also put into exec file, including **exec_config** command, so they can be organised in nested way. **settings** portion of INI file can contain path to cfg file which will be executed each time client is started.

**exec_config** command:
```
  exec_config
  Usage: exec_config [OPTIONS]

  Options:
    --exec_file TEXT
    --help            Show this message and exit.
```


## gNMI service

gNMI service provides Get, Set, Capabilities and Subscribe RPCs described in [gnmi proto file](https://github.com/openconfig/gnmi/blob/master/proto/gnmi/gnmi.proto) with documentation for: [service](https://github.com/openconfig/gnmi/blob/master/proto/gnmi/gnmi.proto), [authentication](https://github.com/openconfig/reference/blob/master/rpc/gnmi/gnmi-authentication.md) and [path conventions](https://github.com/openconfig/reference/blob/master/rpc/gnmi/gnmi-path-conventions.md).


### Configuration mode limitations

Classic SROS configuration mode provides access only to state tree via Get and Subcribe RPCs. Mixed and model-driven modes provides access to complete config and state tree and in addition to config retrieval, you can also use Set RPC to modify the configuration.

### gNMI Set RPC

Unlike md-cli or netconf, gNMI JSON encoding requires proper mapping of element data types described in
[RFC 7951](https://github.com/openconfig/gnmi/blob/master/proto/gnmi/gnmi.proto). While this is ok for clients that can parse schema from YANGs,
grpc_shell doesnt support this capability yet and by default does only best effort when guessing types of fields. In case you want to for example set element which is defined as uint64 to value 3, grpc_shell doesnt know that it has to be encoded as string. In that case you have to manually specify also types for each name value pair.

Another distinction of Set RPC is that from external POV it cannot work with candidate database and therefore doesnt contain extra messages for validation and commit. These are automatically performed as part of each RPC.

Set rpc provides three operations - delete, replace and update, **this particular order is enforced by proto specification**. This means that if multiple operations are specified in one RPC, first all deletes will be performed, then all replaces and then all updates.

#### Examples

Lets say we have interface on Base router and we want to delete all egress filters, replace ipv4 config and update its description, admin-state and cpu-protection.

First we can specify delete operation which accepts only path, we dont have to worry about data types inside paths, as all elements are considered to be string:
```
gnmi_set delete /configure/router[router-name=Base]/interface[interface-name=test]/egress/filter
```

Then we can replace ipv4 primary address operation. Following command will restore everything under primary container to default values and then perform update on specified values:
```
gnmi_set replace /configure/router[router-name=Base]/interface[interface-name=test]/ipv4/primary --values address 1.2.3.4 --values prefix-length 24
```

Update operation is similiar to replace but it performs just merge operation and doesnt change fields that are not specified within the message:
```
gnmi_set update /configure/router[router-name=Base]/interface[interface-name=test] --values admin-state enable --values description ipv4_interface --values cpu-protection 254
```

Since in all the commands above we worked under interface context, we can use prefix subcommand and all paths in succeeding commands will start from that point, so procedure performed above would look like this:
```
gnmi_set prefix /configure/router[router-name=Base]/interface[interface-name=test]
gnmi_set delete /egress/filter
gnmi_set replace /ipv4/primary --values address 1.2.3.4 --values prefix-length 24
gnmi_set update / --values admin-state enable --values description ipv4_interface --values cpu-protection 254
```

Note that in last command we will specify just / without any elements as we want to continue right where prefix ends.

In case we need to deal with tricky typing of yang data types to JSON datatypes, you can manually override the type casting like this:
```
gnmi_set update /configure/test/container-units/container-rates --values leaf-terabps 2  --types string  --values leaf-gigabps 1 --types string
```

**Prefix is common for whole RPC.**


### gNMI Get RPC

Get is unary RPC for data retrieval which means that there is one request with set of paths and one respone with set of notifications which contain all the requested data. Whole dataset must be collected and serialized on remote side (router), so queries for large amount of data might fail because of unsufficient amount of system resources.

#### Examples

Same as Set RPC, you can use prefix to shorten all further paths in GetRequest. By default both state (config false) and config data are returned, this can be optionally filtered by setting 'type' in request. If you query path where syntax and schema is correct, but there is no such object in database, no data is returned.

This set of commands will ask for every config and state element on router:
```
gnmi_get path /state
gnmi_get path /configure
gnmi_get execute
```

This will ask for state but use type filter for config, so this request will always return empty:
data:
```
gnmi_get type config
gnmi_get path /state
gnmi_get execute
```


### gNMI Subscribe RPC

Subscribe RPC allows the client to create subscription which is long lived channel between client and remote side. Depending on the mode of subscription, the remote side will stream data when certain trigger on remote is activated (STREAM mode), or when client asks for it (POLL mode) or only once and then the remote will destroy the subscription (ONCE mode).


POLL, ONCE and STREAM modes apply to whole subscription. ON_CHANGE and SAMPLE modes can be specified with each path. **If you dont specify any mode, it defaults to TARGET_DEFINED**, which is ON_CHANGE for all supported ON_CHANGE paths and SAMPLED for the rest. ON_CHANGE is supported by all config leafs and subset of state leafs (on SROS these paths can be obtained with command `tools dump system telemetry on-change-paths`).

When no interval is specified in subscribe command for streaming request, minimal value for this option is assumed by SROS. For 16.* release train its 10 seconds, for 19.* and later its 1 second.

To completely remove subscription from session use **destroy command**.

You can change output target of notifications to file insted of stdout with log command executed before subscriptions starts:
```
gnmi_subscribe log --file_path /home/jack/subs_file
```

#### Examples

Subscribe to two paths - state in sample mode, config in on_change. Once you have data
you wanted you can cancel RPC:

```
gnmi_subscribe subscribe /configure --interval 10 --trigger ON_CHANGE
gnmi_subscribe subscribe /state/router[router-name=Base] --interval 10 --trigger
SAMPLE
gnmi_subscribe execute
gnmi_subscribe cancel
gnmi_subscribe destroy
```

While you can specify interval also for on_change subscriptions like in example above, it is ignored by remote side.

## RibApi Service

RibApi service provides Modify and GetVersion RPCs.

### Configuration mode limitations

There are no limitations regarding configuration modes for RibApi service.

### RibApi Modify RPC

Bidirectional streaming RPC which provides calls to add, replace or delete RIB entries in IPv4/IPv6 route, IPv4/IPv6 tunnel and MPLS lable tables. Context of this RPC is not destroyed after each operation, so client can push any number of requests towards remote side within the same HTTP2 stream. Responses to these queries are synchronously generated by remote side. in grpc_shell tool, context is created after first execution of the RPC, all succeeding requests are sent on the same context until the user or remote side manually calls cancel on RPC or connection is lost for some reason (network problem, reboot, switchover).

Each command that can be specified inside ModifyRequest as Request has to have its id unique to its RPC lifetime. If you dont specify this number, grpc_shell will automatically assign number to Request in incremental manner.

Once you are done specifing commands you want to send in one batch, you can execute them with rib_modify --name `<my_rpc_name>` execute and subsequently call rib_modify --name `<my_rpc_name>` block if working with larger scale.

#### Examples

Commands to manipulate router and table entries have following syntax:
```
rib_modify <table> <operation> <table_specifier> [OPTIONS]
```

Syntax for label entries is similiar with the exception of `<table_specifier>` which is left out.

Following combinations are currently supported:
```
rib_modify route add ipv4 <OPTIONS>
rib_modify route replace ipv4 <OPTIONS>
rib_modify route delete ipv4 <OPTIONS>
rib_modify route add ipv6 <OPTIONS>
rib_modify route replace ipv6 <OPTIONS>
rib_modify route delete ipv6 <OPTIONS>
rib_modify tunnel add ipv4 <OPTIONS>
rib_modify tunnel replace ipv4 <OPTIONS>
rib_modify tunnel delete ipv4 <OPTIONS>
rib_modify tunnel add ipv6 <OPTIONS>
rib_modify tunnel replace ipv6 <OPTIONS>
rib_modify tunnel delete ipv6 <OPTIONS>
rib_modify label add <OPTIONS>
rib_modify label replace <OPTIONS>
rib_modify label delete <OPTIONS>
rib_modify next_hop_switch <OPTIONS>
```

While NextHopGroup can be send only within tunnel or label entry, it has separate command on rib_modify level because of complexity and repeated nature of the message. So during adding NextHopGroup group to one of the entries you have to maunally add also request id you wish to modify or grpc_shell will automatically add the group to last created entry.

Entering request_id manually:
```
rib_modify tunnel add ipv4 --id 1 --key_endpoint 10.20.1.6
rib_modify tunnel add ipv4 --id 2 --key_endpoint 10.20.1.6
rib_modify next_hop_group --request_id 1 --group_id 1 --backup_ip 5.6.7.8 --backup_labels "1,2" --primary_ip 1.2.3.4 --primary_labels '23'
```

Will result in message like this:

```
(vacica) > rib_modify
Modify - default_modify

UNPROCESSED REQUESTS:

======= id: 1 =======
==request 1:
id: 1
ipv4_tunnel_ADD {
  entry_key {
    endpoint: "10.20.1.6"
  }
  groups {
    id: 1
    primary {
      ip_address: "1.2.3.4"
      pushed_label_stack: 23
    }
    backup {
      ip_address: "5.6.7.8"
      pushed_label_stack: 1
      pushed_label_stack: 2
    }
  }
}


======= id: 2 =======
==request 2:
id: 2
ipv4_tunnel_ADD {
  entry_key {
    endpoint: "10.20.1.6"
  }
}


Error:
None
```

Specifing commands without ids:
```
rib_modify tunnel add ipv4 --key_endpoint 10.20.1.6
rib_modify tunnel add ipv4 --key_endpoint 10.20.1.6
rib_modify next_hop_group --group_id 1 --backup_ip 5.6.7.8 --backup_labels "1,2" --primary_ip 1.2.3.4 --primary_labels '23'
```

Will result in this message:
```
Modify - default_modify

UNPROCESSED REQUESTS:

======= id: 1 =======
==request 1:
id: 1
ipv4_tunnel_ADD {
  entry_key {
    endpoint: "10.20.1.6"
  }
}


======= id: 2 =======
==request 2:
id: 2
ipv4_tunnel_ADD {
  entry_key {
    endpoint: "10.20.1.6"
  }
  groups {
    id: 1
    primary {
      ip_address: "1.2.3.4"
      pushed_label_stack: 23
    }
    backup {
      ip_address: "5.6.7.8"
      pushed_label_stack: 1
      pushed_label_stack: 2
    }
  }
}


Error:
None
```

## CertificateManagement service

:heavy_exclamation_mark: :skull: None of the certificates, certificate authorities and generally antyhing that is provided by this tool or described in this document shouldnt be used in production enviroment and shouldnt be considered as safe. Certificate provisioning should always happen in already secured network, ideally on secured connection. :skull: :heavy_exclamation_mark:


CertificateManagement service provides Rotate, Install, GetCertificates (not implemented yet), RevokeCertificates (not implemented yet) and CanGenerateCSR RPCs described in [cert.proto](https://github.com/openconfig/gnoi/blob/master/cert/cert.proto). Some additional documents can be found in [gnoi docs](https://github.com/openconfig/gnoi/tree/master/docs). This shell works exclusively with [x509 certificates](https://tools.ietf.org/html/rfc5280) and uses PEM for persisent storage and exchange of information between objects within shell.

Rotate and Install can both manipulate certificates on target, detailed description of message flows is in proto file. TL;DR version:
 - Install is used to push new certificates to target, the RPC fails in case certificate with identical id already exists.
 - Rotate is used to replace existing certificates on target, the RPC failn in case certificate with identiacal id does not already exists.

Besides classic RPC commands, shell introduces certificate manager, which holds certificate objects. These objects provides interface to generate and store CSR, certification authories and certificates itself. All currently loaded cert objects can be viewed by ```show certificates``` command.

On SROS you will have to enable the service under grpc server configuration and permit the RPC in your aaa profile, md-cli:
```
/configure system grpc gnoi cert-mgmt admin-state enable
/configure system security aaa local-profiles profile "dummy" grpc rpc-authorization gnoi-cert-mgmt-rotate permit
/configure system security aaa local-profiles profile "dummy" grpc rpc-authorization gnoi-cert-mgmt-install permit
/configure system security aaa local-profiles profile "dummy" grpc rpc-authorization gnoi-cert-mgmt-getcert permit
/configure system security aaa local-profiles profile "dummy" grpc rpc-authorization gnoi-cert-mgmt-revoke permit
/configure system security aaa local-profiles profile "dummy" grpc rpc-authorization gnoi-cert-mgmt-cangenerate permit
```

#### Examples
Certificate manager is available via cert command. In each scenario we will need to create certification(CA) authority to sign and later verify our certificates.

##### Install RPC with CSR from target
Simple CA can be created and persitently saved with commands:
```
cert --name ca params --common_name ca.vacica.com --organization "Vacica Inc." --not_valid_before_days 1 --not_valid_after_days 30  --add_target_ip
cert --name ca create_ca
cert --name ca save certificate --path /tmp/ca_test.pem
cert --name ca save key --path /tmp/ca_test.key
```

Further scenarios revolve around abilty of target to genenerate CSR. SROS has this capabaility, so we can create another cert object, which will hold some basic information send in the RPC. The same object will be later used to sign the certificate and hold the pem text which we can load to target:
```
cert --name test_cert_install params --hostname test.vacica.com --common_name test.vacica.com --organization "Vacica Inc." --organizational_unit "RnD" --country SK --state SK --city "Bratislava" --not_valid_before_days 1 --not_valid_after_days 30  --email_id test-vacica@vacica.com --add_target_ip
```
Special switch ```--add_target_ip``` will automatically put IP address of target to list of addresses in certificate. Additional IPs can be specified by repeated option ```--ip_addr```, but SROS implementation of CSRParams message can currently parse only one address per certificate.

Now we can instantiate install RPC and ask target to provide CSR based on information in cert object created in previous step:
```
gnoi_cert --name install_rpc_test --cert_object test_cert_install --rpc install
gnoi_cert --name install_rpc_test generate_csr
```

In case the RPC was successful, CSR is loaded in cert object and ready to be signed by CA created if first step:
```
cert --name test_cert_install issue_certificate --ca_name ca
```

In last step, we need to upload the certificate to target and just in case we can also persitently store it on disk:
```
gnoi_cert --name install_rpc_test load_certificate
cert --name test_cert_install save csr --path /tmp/csr_test_cert_install.pem
cert --name test_cert_install save certificate --path /tmp/cert_test_cert_install.pem
```

The certificate is now available on target, you can check wheter it is present in system-pki directory on target compact flash:
```
*A:Dut-C# file dir cf1:/system-pki/ 

Volume in drive cf1 on slot A is CF1.

Volume in drive cf1 on slot A is formatted as FAT32

Directory of cf1:\system-pki\

12/05/2019  04:08a      <DIR>          ./
12/05/2019  04:08a      <DIR>          ../
12/05/2019  01:00p                 901 install_rpc_test.crt
12/05/2019  01:00p                1255 install_rpc_test.key
               2 File(s)                   2156 bytes.
               2 Dir(s)              8573140992 bytes free.

```


##### Rotate RPC with CSR from target
Commands for Rotate RPC are very similiar to install, for demo pursposes we will create the same CA, upload one certificate to target via Install RPC and then rotate it via Rotate RPC with same certificate id:

CA and initial install:
```
cert --name ca params --common_name ca.vacica.com --organization "Vacica Inc." --not_valid_before_days 1 --not_valid_after_days 30  --add_target_ip
cert --name ca create_ca
cert --name ca save certificate --path /home/matibens/certs/ca_test.pem
cert --name ca save key --path /home/matibens/certs/ca_test.key

cert --name test_cert_rotate params --hostname test.vacica.com --common_name test.vacica.com --organization "Vacica Inc." --organizational_unit "RnD" --country SK --state SK --city "Bratislava" --not_valid_before_days 1 --not_valid_after_days 30  --email_id test-vacica@vacica.com --add_target_ip
gnoi_cert --name rotate_rpc_test --cert_object test_cert_rotate --rpc install
gnoi_cert --name rotate_rpc_test generate_csr
cert --name test_cert_rotate issue_certificate --ca_name ca
gnoi_cert --name rotate_rpc_test load_certificate
cert --name test_cert_rotate save csr --path /home/matibens/certs/csr_test_cert_rotate.pem
cert --name test_cert_rotate save certificate --path /home/matibens/certs/cert_test_cert_rotate.pem
```

Destroy the original cert object and rpc:
```
gnoi_cert --name rotate_rpc_test destroy
cert --name test_cert_rotate remove
```

And create Rotate RPC with identical certificate id (```gnoi_cert --name```), note the extra finalize call at the end of the sequence required by service:
```
cert --name test_cert_rotate params --hostname test.vacica.com --common_name test.vacica.com --organization "Possum Inc." --organizational_unit "RnD" --country SK --state SK --city "Bratislava" --not_valid_before_days 1 --not_valid_after_days 30  --email_id test-vacica@vacica.com --add_target_ip
gnoi_cert --name rotate_rpc_test --cert_object test_cert_rotate --rpc rotate
gnoi_cert --name rotate_rpc_test generate_csr
cert --name test_cert_rotate issue_certificate --ca_name ca
gnoi_cert --name rotate_rpc_test load_certificate
gnoi_cert --name rotate_rpc_test finalize
```

##### Locally created CSR
CSR can be also created locally by cert manager, so we can skip one step in communication with target and use ```key_pair``` message from service to provide private and public key from cer object.

Obligatory CA:
```
cert --name ca params --common_name ca.vacica.com --organization "Vacica Inc." --not_valid_before_days 1 --not_valid_after_days 30  --add_target_ip
cert --name ca create_ca
cert --name ca save certificate --path /home/matibens/certs/ca_test.pem
cert --name ca save key --path /home/matibens/certs/ca_test.key
```

As in previous examples, create cert object, but this time call generate_csr within the cert manager:
```
cert --name test_cert params --hostname test.vacica.com --common_name test.vacica.com --organization "Vacica Inc." --organizational_unit "RnD" --country SK --state SK --city "Bratislava" --not_valid_before_days 1 --not_valid_after_days 30  --email_id test-vacica@vacica.com --add_target_ip
cert --name test_cert generate_csr
cert --name test_cert issue_certificate --ca_name ca
```

And just upload the certificate with ```--local_keys``` switch:
```
gnoi_cert --name install_rpc_test --cert_object test_cert --rpc install
gnoi_cert --name install_rpc_test load_certificate --local_keys
```

Done, dont hesitate to raise issue in case you encounter any problem.
