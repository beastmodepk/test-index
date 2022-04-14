#!/usr/bin/env python3
'''
Script to send add, remove, deprecate requests to IIB

PRE_REQs:
1. Create .env file with correct overwrite_from_index_token
2. iib-stage.keytab and iib.keytab are present in working directory
3. Create input file with bundles to run operations on (For add/deprecate operations)


example-run:
./bundle_operations.py prod deprecate -v 4.5 -b example-bundles.in --dryrun
Would deprecate these bundles in prod 4.5 index
0: registry.redhat.io/example-bundle-1@sha256:000
1: registry.redhat.io/example-bundle-2@sha256:123

'''

import subprocess
import os
import sys
import json
from dotenv import load_dotenv
import argparse
import requests
from requests_kerberos import HTTPKerberosAuth


parser = argparse.ArgumentParser(
    description="Perform add,remove,deprecation operations with IIB")

parser.add_argument('enviroment', choices=[
                    'prod', 'stage'], help="choose enviroment: stage or prod")
parser.add_argument('operation', choices=[
                    'add', 'deprecate', 'remove'], help="choose operation: add, remove, deprecate")
parser.add_argument('-v', '--version', nargs='+', required=True,
                    help="insert index version to run operation on")
parser.add_argument('-b', '--bundle',
                    required='add' in sys.argv or 'deprecate' in sys.argv,
                    help="insert input file with bundles")
parser.add_argument('-o', '--operator', nargs='+', required='remove' in sys.argv,
                    help="insert operator name to remove")
parser.add_argument('--dryrun', required=False,
                    help="dry run", action='store_true')

args = parser.parse_args()


request_url = {
    'add': 'https://iib.engineering.redhat.com/api/v1/builds/add',
    'deprecate': 'https://iib.engineering.redhat.com/api/v1/builds/add',
    'remove': 'https://iib.engineering.redhat.com/api/v1/builds/rm'
}

stage = {
    'from_index': "registry-proxy.engineering.redhat.com/rh-osbs/iib-pub-pending:v",
    'bundle_prefix': "registry.stage.redhat.io/",
    'principal': "iib-stage@REDHAT.COM",
    'realm': "iib-stage.keytab"
}

prod = {
    'from_index':  "registry-proxy.engineering.redhat.com/rh-osbs/iib-pub:v",
    'bundle_prefix': "registry.redhat.io/",
    'principal': "iib@REDHAT.COM",
    'realm': "iib.keytab"
}


enviroments = {'stage': stage, 'prod': prod}


def get_payload(version):

    load_dotenv()
    payload = {}
    overwrite_from_index_token = os.environ.get("overwrite_from_index_token")
    if overwrite_from_index_token is not None or args.dryrun:
        payload = {"from_index": enviroments[args.enviroment]['from_index'] + version,
                   "overwrite_from_index": True,
                   "overwrite_from_index_token": overwrite_from_index_token}
    else:
        raise Exception("overwrite_from_index_token missing in .env file")

    if args.bundle is not None:
        with open(args.bundle) as bundle_file:
            bundle_list = []
            for i in bundle_file:
                bundle = enviroments[args.enviroment]['bundle_prefix'] + i
                bundle_list.append(bundle.strip())

    if args.operation == "add":
        payload['bundles'] = bundle_list
    elif args.operation == "deprecate":
        payload['deprecation_list'] = bundle_list
    elif args.operation == "remove":
        payload['operators'] = args.operator

    return payload


def main():
    for version in args.version:
        payload = get_payload(version)
        if args.dryrun:
            if args.operation == "remove":
                print("Would remove {} from {} {} index".format(
                    str(payload['operators'])[1:-1], args.enviroment, version))
            else:
                print("Would {} these bundles in {} {} index".format(
                    args.operation, args.enviroment, version))
                print(*('{}: {}'.format(*k)
                        for k in enumerate(list(payload.values())[-1])), sep="\n")
                print("-"*50)
        else:
            kinit = ['kinit', '-kt', enviroments[args.enviroment]
                     ['realm'], enviroments[args.enviroment]['principal']]
            url = request_url[args.operation]
            header = {'Content-Type': 'application/json', }

            subprocess.run(['kdestroy', '-A'])
            subprocess.run(kinit)
            response = requests.post(url, headers=header, data=json.dumps(
                payload), auth=HTTPKerberosAuth())

            if response.status_code == 201 and response.json()['logs']['url'] is not None:
                print("IIB request for {} {}".format(
                    version, response.json()['logs']['url']))
            else:
                print("Request failed with response: {}".format(response.json()))

            subprocess.run(['kdestroy', '-A'])


if __name__ == "__main__":
    main()
