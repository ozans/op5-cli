![alt text](https://travis-ci.org/ozans/op5-cli.svg?branch=master "travis build status")

op5-cli
========
A command-line interface for the OP5 monitoring system using its REST API

How to install
----------
```
pip install -r requirements.txt
python setup.py install
```

How to run
----------
 `$ op5-cli <action_type> <object_type> [<name>] [--data <data>]`

The program will output (only) valid JSON data on success; making it easy for the output to be piped into external tools (e.g. JSON parsers like jq) to be processed further.

Examples
----------
 `$ op5-cli read host <host_name>`

 `$ op5-cli read hostgroup <hostgroup_name>`

 `$ op5-cli read hostgroup ""` #use an empty name to list all objects of the given object type

 `$ op5-cli read service "<host_name>|<hostgroup_name>;<service_description>"`

 `$ op5-cli create host --data "$(<example_data/host_data)"`

 `$ op5-cli update host <host_name> --data "$(<example_data/passive_host_data)"`

 `$ op5-cli create host --data '{"host_name":"test"}'`

 `$ op5-cli delete host test`

 `$ op5-cli create service --data "$(<example_data/service_data)"`

 `$ op5-cli overwrite service "<host_name>|<hostgroup_name>;<service_description>" --data "$(<example_data/passive_service_data)"`

Contributing
------------
Pull requests, bug reports, and feature requests are extremely welcome.
