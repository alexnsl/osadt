#!/usr/bin/env python

"""

OSA deployment tool.

Prerequisites:

0. It works only on LINMN

Modify options in CONFIGURATION section.

In some specific cases you might need to adjust the code itself.

"""

####### CONFIGURATION ############

licurl = 'http://internal.local/PA.1234567890.xml'
# or uncomment below and comment above to install from file
# licfile = '/path/to/licencse' 

provdomain = 'prov.tld'
cp_password = 'secret'

brand_attr = 'branding'
linpgh_attr = 'External Provisioning'

# uncomment if CP uses exclusive IP
#cp_ip = 'PCP.IP.ADD.RESS'
#cp_ipnetmask = '255.255.255.0'

# brand will be created at https://cp.prov.tld
cp_prefix = 'cp'
# if cp is not subdomain of provdomain, uncomment below:
# cp_domain='cp.some.tld'

# SSH creds
login = 'ssh username for nodes'
password = 'ssh password'
# if nodes are using different passwords, modify it in osa.calls(...)

# NODES
# if there is no some node, delete it from nodes dictionary.
nodes = {
    'linpps': {'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
    'linpgh': {'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
    'nses': [
        {'hostname': '<CHANGE>', 'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
        {'hostname': '<CHANGE>', 'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
    ],
    'ui': {'frontnet': '<CHANGE>', 'backnet': '<CHANGE>' },
    'ba': {
        'db': {'backnet': '<CHANGE>'},
        'app': {'hostname': '<CHANGE>', 'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
        'store': {'hostname': '<CHANGEORDELETE>', 'frontnet': '<CHANGE>', 'backnet': '<CHANGE>'},
    }
}


############## CONFIGURATION END #################


from osadt import OSA
osa = OSA(cp_password=cp_password)

# install license
if 'licfile' in globals():
    osa.upload_license(filename=licfile)
else:
    osa.upload_license(url=licurl)

# add provider's domain
domain_id = osa.add_provider_domain(provdomain)

# privacy proxy
node = nodes.get('linpps')
if node:
    osa.register_linpps(node['backnet'], login, password, node['frontnet'])

# linpgh
node = nodes.get('linpgh')
if node:
    osa.create_attrs(linpgh_attr)
    node_id = osa.register_shared_node(node['backnet'], login, password, node['frontnet'])
    osa.set_host_attrs(node_id, linpgh_attr)
    osa.set_host_ready(node_id)
 
# nses
nses = nodes.get('nses')
if nses:
    ns_hostnames = [node['hostname'] for node in nses]
    for node in nses:
        osa.register_dns(node['backnet'], login, password, node['frontnet'],
            new_hostname=node.get('hostname'))
    osa.create_dns_rt(*ns_hostnames)
    osa.add_dns_hosting(provdomain)
    # add A records
    for node in nses:
        ns_hostname = node['hostname']
        ns_fip = node['frontnet']
        # subdomain of provdomain?
        if ns_hostname.endswith('.' + provdomain):
            prefix = ns_hostname[:-len(provdomain)-1]
            osa.add_dns_record(provdomain, prefix, 'A', ns_fip)
 
# UI host
node = nodes.get('ui')
if node:
    branding_host_id = osa.register_wsng(node['backnet'], login, password,
        node['frontnet'])
    osa.add_ui(branding_host_id)
    osa.create_attrs(brand_attr)
    osa.set_host_attrs(branding_host_id, brand_attr)
    osa.set_host_ready(branding_host_id)
    # configure RTs for branding
    bap_rt_id = osa.get_rt_id('Branding access points', 'Branding access points')
    osa.set_rt_attrs(bap_rt_id, brand_attr)
    brand_web_rt_id = osa.create_brand_web_rt(provdomain, brand_attr=brand_attr)
    if 'cp_domain' in globals():
        osa.add_provider_domain(cp_domain)
    else:
        cp_domain = cp_prefix + '.' + provdomain
        osa.add_provider_subdomain(provdomain, cp_prefix)
    has_exclusive_ip = 'cp_ip' in globals()
    if has_exclusive_ip:
        # create branding ip pool
        pool_id = osa.create_ip_pool(cp_domain, cp_ip, cp_ip, cp_ipnetmask,
            ['COMMON.BRANDING', 'SHARED.HOSTING'])
        osa.bind_ip_pool(branding_host_id, node['frontnet'], pool_id)
    osa.create_prov_brand(cp_domain, has_exclusive_ip) 
 
######## BA deployment
ba = nodes.get('ba')
if ba:
    osa.register_badb(ba['db']['backnet'], login, password, ba['app']['backnet'])
    osa.register_baapp(ba['app']['backnet'], login, password, ba['app']['frontnet'],
        ba['app']['hostname'])
    osa.register_store(ba['store']['backnet'], login, password, ba['store']['frontnet'],
        ba['store'].get('hostname')) 





# if modeline is not enabled, run 'set modeline | doautocmd BufRead' in vim
# vim: tabstop=4:softtabstop=4:shiftwidth=4:textwidth=100:expandtab:autoindent:fileformat=unix
