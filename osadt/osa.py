import time
import urllib2
import xmlrpclib
import subprocess

from poaupdater import openapi
from poaupdater import uPackaging
from poaupdater import uSysDB
from poaupdater.openapi import OpenAPIError

import poaupdater.uLogging
from poaupdater.uConfig import *
poaupdater.uLogging.log_to_console = False
poaupdater.uLogging.logfile = open('poaupdater.log', 'w')

class OSAError(Exception):
    pass


class OSA:

    api_sync_timeout = 30
    register_shared_node_timeout = 600
    install_package_timeout = 300
    add_dns_hosting_timeout = 330
    check_period = 5

    def __init__(self, cp_login='admin', cp_password=None, cp_url='http://127.0.0.1:8080/'):
        config = Config()
        openapi.initFromEnv(config)
        self.api = openapi.OpenAPI()
        self.cp_login = cp_login
        self.cp_password = cp_password
        self.cp_url = cp_url

    @staticmethod
    def install_updates(install_updates_cmd):
        check = ""
        while check != "ignore":
            try:
                check = ""
                subprocess.check_call(install_updates_cmd, shell=True)
                break
            except subprocess.CalledProcessError as e:
                print("Install updates command: {}; failed with output {}".format(install_updates_cmd, e.output))
                while check not in {'retry', 'abort', 'ignore'}:
                    check = raw_input("Update installation failed, retry/abort/ignore: ")
                if check == "retry" or check == "ignore":
                    pass
                if check == "abort":
                    exit(1)

    def api_async_call(self, methodname, **kwargs):
        """Run async api call

        :returns: (request_id, response)
        """
        #TODO lock api until commit
        method = getattr(self.api, methodname)
        request_id = self.api.beginRequest()
        result = method(**kwargs)
        self.api.commit()
        return request_id, result
    
    def api_async_call_wait(self, methodname, timeout=None, **kwargs):
        """Run async api call and wait till execution

        :returns: response from api call
        :raises OSAError: in case of timeout or API call failure
        """
        timeout = timeout or self.api_sync_timeout
        start_time = time.time()
        request_id, result = self.api_async_call(methodname, **kwargs)
        while True:
            status = self.api.pem.getRequestStatus(request_id=request_id)
            if status['request_status'] == 0:
                return result
            elif status['request_status'] == 2:
                raise OSAError("Failure while executing {0} with args {1}, status: {2}"
                    .format(methodname, kwargs, status))
            if time.time() - start_time > timeout:
                raise OSAError("Timeout ({2}) while executing {0} with args {1}"
                    .format(methodname, kwargs, timeout))
            time.sleep(self.check_period)

    def api_getMethodSignature(self, method_name):
        method = getattr(self.api.server,'pem.getMethodSignature')
        return method({ 'method_name' : method_name }).get('signature', None)

    def upload_license(self, url=None, filename=None, lic=None):
        """Upload license

        Either url or filename or lic should be set

        :param url: URL from which license can be downloaded
        :param filename: path to the license file
        :param lic: license
        :returns: nothing
        :raises OSAError: in case of wrong creds
        """
        if not (url or filename or data):
            raise OSAError("No url or filename or lic were passed")
        if url:
            lic = urllib2.urlopen(url).read()
        elif filename:
            with open(filename, "r") as f:
                lic = f.read()
        self.api_async_call_wait('pem.uploadLicense', license=xmlrpclib.Binary(lic))

    def get_domain(self, name):
        """Find domain by name
        
        :returns: tuple (domain_id, owner_id)
        """
        try:
            res = self.api_async_call_wait('pem.getDomainByName', domain_name=name)
        except OpenAPIError as err:
            # no such domain?
            if err.module_id == 'dns' and err.extype_id == 10:
                return None, None
            else:
                raise
        else:  # domain found
            return res['domain_id'], res['owner_id']

    def add_domain(self, acc_id, name):
        """Add domain without hosting

        Reentarable
        :returns: domain id
        :raises OSAError: when domain exists with wrong owner
        """
        # check if domain exists
        domain_id, owner_id = self.get_domain(name)
        if domain_id:  # domain exists
            if owner_id == acc_id:  # owner is the same
                return domain_id
            else:
                raise OSAError("Domain {0} exists and belongs to different owner, id: {1}"
                    .format(name, owner_id))
        else:  # no such domain, create
            res = self.api_async_call_wait('pem.addDomainToAccount',
                account_id=acc_id, domain_name=name)
            return res['domain_id']

    def add_provider_domain(self, name):
        """Create domain on provider level

        Reenterable
        :returns: domain id
        """
        return self.add_domain(1, name)

    def add_subdomain(self, sub_id, domain, prefix):
        """Add subdomain prefix.domain

        Reenterable
        :returns: subdomain id
        :raises OSAError: when subdomain exists with wrong subscription
        """
        subdomain = prefix + '.' + domain
        # check if subdomain exists
        subdomain_id, owner_id = self.get_domain(subdomain)
        if subdomain_id:  # subdomain exists
            # check that subscription belongs to the same owner
            res = self.api_async_call_wait('pem.getSubscription',
                subscription_id=sub_id, get_resources=False)
            if owner_id == res['owner_id']:
                return subdomain_id
            else:
                raise OSAError("Subdomain {0} exists and belongs to different owner, id: {1}. Subscription {2} belongs to {3}"
                    .format(subdomain, owner_id, sub_id, res['owner_id']))
        else:  # no subdomain, create
            res = self.api_async_call_wait('pem.addSubdomain',
                subscription_id=sub_id, domain_name=domain, prefix=prefix)
            return res['domain_id']

    def add_provider_subdomain(self, domain, prefix):
        """Add subdomin prefix.domain for provider

        :returns: subdomain id
        """
        return self.add_subdomain(1, domain, prefix)

    def register_shared_node(self, backnet, login, password, frontnet=None,
        new_hostname=None, role=None, role_params=None):
        """Register node

        Reenterable
        :returns: node id
        """
        shared_ip = frontnet or backnet
        net_conf = {'communication_ip': backnet, 'shared_ip': shared_ip}
        _role_params = None
        if role_params:
            _role_params = [ {'name': n, 'value': v} for n, v in role_params.items() ]
        try:
            res = self.api_async_call_wait('pem.registerSharedNode',
                timeout=self.register_shared_node_timeout,
                host=backnet, login=login, password=password,
                network_config=net_conf, new_hostname=new_hostname,
                role=role, role_params=_role_params)
        except OpenAPIError as err:
            # node is registered already?
            if err.module_id == 'SharedNodeRegistrator' and err.extype_id == 13:
                host = self.api_async_call_wait('pem.getHosts',ip_address=backnet)
                return int(self.get_hostid_by_ip(backnet))
            else:
                raise
        return res.get('host_id')

    def install_package(self, host_id, name, ctype, properties=None):
        """Install package to host

        Reenterable
        :param ctype: is one of service, sc, cp, other
        :returns: component_id
        """
        try:  # check if already installed
            component_id, version = uPackaging.findHostComponentId(host_id, name, ctype)
        except uPackaging.ComponentNotFound:
            pass
        else:
            return component_id
        pkg_id, version = uPackaging.findSuitablePackage(host_id, name, ctype)
        if properties is None:
            proplist = []
        else:
            proplist = [ { "name" : name, "value" : value } 
                for (name, value) in properties.items() ]
        res = self.api_async_call_wait('pem.packaging.installPackageSync',
            timeout=self.install_package_timeout,
            host_id=host_id, package_id=pkg_id, properties=proplist)
        return res.get('component_id')

    def install_packages(self, host_id, packages):
        """Install multiple packages to the host

        :param packages: list of: [ { 'name': name, 'ctype': ctype, 'properties': properties }, ..]
        """
        for package in packages:
            self.install_package(host_id, **package)

    def set_host_attrs(self, host_id, *attrs):
        """Set provisioning attributes for the host"""
        self.api_async_call_wait('pem.setHostAttributes',
            host_id=host_id, attr=attrs)

    def set_host_ready(self, host_id, ready=True):
        """Set host ready to provide
        
        :param ready: if False - unset
        """
        self.api_async_call_wait('pem.setHostReadyToProvide',
            host_id=host_id, ready_to_provide=ready)

    def create_attrs_w_d(self, attrs):
        """Create provisioning attributes with descriptions.

        Example osa.create_attrs_w_d({'attr1': 'descr1', 'attr2': 'descr2', ..})
        Reenterable
        """
        # filter existing attrs
        res = self.api_async_call_wait('pem.getProvisioningAttributes')
        existing = [ a['name'] for a in res ]
        _attrs = [ {'name': name, 'descr': descr}
            for (name, descr) in attrs.items() if not name in existing ]
        if not _attrs:
            return
        self.api_async_call_wait('pem.addProvisioningAttributes', attrs=_attrs)

    def create_attrs(self, *attrs):
        """Create provisioning attributes

        Example osa.create_attrs('attr1', 'attr2', ..)
        Reenterable
        """
        _attrs = dict( (name, '') for name in attrs )
        self.create_attrs_w_d(_attrs)

    def get_rt_id(self, rt_name, rt_class):
        """Find resource type

        :returns: rt_id of the first found
        """
        res = self.api_async_call_wait('pem.getResourceTypesByClass',
            resclass_name=rt_class, show_system_rt=True)
        for rt in res:
            if rt['resource_type_name'] == rt_name:
                return rt['resource_type_id']
        # not found? search by class friendly name
        res = self.api_async_call_wait('pem.getResourceTypesByClass',
            friendly_name=rt_class, show_system_rt=True)
        for rt in res:
            if rt['resource_type_name'] == rt_name:
                return rt['resource_type_id']
        return None

    def set_rt_attrs(self, rt_id, *attrs):
        """Set provisioning attributes for the resource type"""
        self.api_async_call_wait('pem.setRTAttributes',
            rt_id=rt_id, attr=attrs)

    def create_rt(self, rt_name, rt_class, params=None, attrs=None, descr=None):
        """Create Resource Type

        Reenterable
        
        :param params: = {'param_name': 'param_value', ...}
        :returns: rt_id
        """
        # check if RT exists
        rt_id = self.get_rt_id(rt_name, rt_class)
        if rt_id:
            return rt_id
        _attrs = attrs or []
        _params = params or {}
        act_params = [ {'var_name': n, 'var_value': v}  for n, v in _params.items() ]
        res = self.api_async_call_wait('pem.addResourceType',
            resclass_name=rt_class, name=rt_name,
            attrs=_attrs, act_params=act_params)
        return res.get('resource_type_id')

    def create_dns_rt(self, *ns_hostnames):
        """Create DNS Hosting Resource Type
        
        :param ns_hostnames: list of nameservers to use
        :returns: rt_id
        """
        # check if RT exists
        #   despite the fact we have the same check in create_rt(),
        #   it is needed here so we do not create additional dns configs
        rt_id = self.get_rt_id('DNS Hosting', 'DNS Hosting')
        if rt_id:
            return rt_id
        _ns_hostnames = {}
        for i, name in enumerate(ns_hostnames, start=1):
            _ns_hostnames['ns' + str(i)+ '_hostname'] = name
        dns_config_id = self.api_async_call_wait('pem.createDNSHostingConfiguration',
            refresh=14400, retry=7200, expire=2419200, min_ttl=3600, **_ns_hostnames)
        return self.create_rt('DNS Hosting', 'DNS Hosting', 
            {'auto_host_domains': 'yes', 'configuration_id': str(dns_config_id)})

    def add_dns_hosting(self, domain, dns_rt_id=None, dns_rt_name='DNS Hosting'):
        """Add dns hosting to domain

        :param dns_rt_id: rt_id of dns hosting resource, optional
        :param dns_rt_name: name of dns hosting resource, predefined 
        """
        dom_id, owner_id = self.get_domain(domain)
        if not dns_rt_id:
            dns_rt_id = self.get_rt_id(dns_rt_name, 'DNS Hosting')
        try:
            self.api_async_call_wait('pem.addDNSHosting',
                timeout=self.add_dns_hosting_timeout,
                domain_id=dom_id, hosting_rt_id=dns_rt_id)
        except OpenAPIError as err:
            # already added?
            if err.module_id == 'dns' and err.extype_id == 2040:
                return
            else:
                raise

    def add_dns_record(self, domain, host, type, data):
        """Create DNS resource record in domain

        :returns: DNS record_id
        """
        try:
            res = self.api_async_call_wait('pem.createDNSRecord',
                timeout=self.add_dns_hosting_timeout,
                domain_name=domain, host=host, type=type, data=data)
            return res['record_id']
        except OpenAPIError as err:
            # already added?
            if err.module_id == 'dns' and err.extype_id == 2061:
                return 0
            else:
                raise

    def create_brand_web_rt(self, provdomain,
        rt_name='Shared hosting Apache (branding)',
        brand_attr='branding'):
        """Create resource type for branding webspace

        Uses resource class Apache Physical Hosting
        :returns: rt_id
        :raises OSAError: when provdomain does not exist
        """
        domain_id, owner_id = self.get_domain(provdomain)
        if not domain_id:
            raise OSAError("Domain {0} not found".format(provdomain))
        return self.create_rt(rt_name, 'apache_physical_hosting',
            {'auto_host_domains': 'yes', 'ds.domain_id': str(domain_id)},
            [brand_attr])

    def register_ui(self, backnet, login, password, frontnet):
        """Register UI node

        Reenterable
        :returns: host_id
        """
        # check if host with this backnet ip exists

        """wbl = webalizer or 'webalizer.default'
        res = self.api_async_call_wait('pem.web_cluster.registerStandaloneWebServer',
            timeout=self.register_shared_node_timeout,
            webserverInfo={'internal_ip': backnet, 'public_ip': frontnet,
                'login': login, 'password': password, 'weight': 32},
            webalizer=wbl, dbInfo=[])
        return res.get('host_id')"""

        host_id = self.register_shared_node(backnet,login,password,frontnet)
        # need to install httpd and mod_ssl manually on the target host.
        install_cmd = "/usr/local/pem/bin/pleskd_ctl -f /usr/local/pem/etc/pleskd.props processHCL install.hcl " + str(host_id)
        check = ""
        while check != "ignore":
            try:
                check = ""
                subprocess.check_call(install_cmd, shell=True)
                break
            except subprocess.CalledProcessError as e:
                print("Installation of httpd/mod_ssl: {}; failed with output {}".format(install_cmd, e.output))
                while check not in {'retry', 'abort', 'ignore'}:
                    check = raw_input("retry/abort/ignore: ")
                if check == "retry" or check == "ignore":
                    pass
                if check == "abort":
                    exit(1)

        self.install_package(host_id,'branding','other')
        self.install_package(host_id,'pui-war','other')
        return host_id

    def get_hostid_by_ip(self,backnet):
        hosts = self.api_async_call_wait('pem.getHosts')
        for h in hosts:
            ips = [ ip['ip_address'] for ip in h['ip_addresses'] ]
            if backnet in ips:
                return h['host_id']
        return -1

    def add_ui(self, cluster_id):
        """Add UI service to NG cluster

        Reenterable
        """
        self.api_async_call_wait('pem.web_cluster.enableAddonService',
            timeout=self.install_package_timeout, clusterID=cluster_id, service='UI')

    def register_dns(self, backnet, login, password, frontnet, new_hostname=None):
        """Register lindns
        
        :returns: host_id
        """
        return self.register_shared_node(backnet, login, password, frontnet, new_hostname, role='DNS_BIND')

    def register_linpps(self, backnet, login, password, frontnet):
        """Register linpps
        
        :returns: host_id
        """
        host_id = self.register_shared_node(backnet, login, password, frontnet)
        self.install_package(host_id, 'PrivacyProxy', 'service')
        return host_id

    def register_pim_sso(self, backnet, login, password, frontnet):
        """Register PIM-SSO server
        Not verified method! I don't know how PIM-SSO should be registered
        :returns: host_id
        """
        return self.register_shared_node(backnet, login, password, frontnet, role='PIM-SSO')

    def register_badb(self, backnet, login, password, bafe_backnet_ip):
        """Register LINBABE server

        :returns: host_id
        """
        return self.register_shared_node(backnet, login, password,
            role='BSS DataBase', role_params={'billing.ip.host': bafe_backnet_ip})

    def register_baapp(self, backnet, login, password, frontnet, ba_fqnd):
        """Register LINBAFE server

        ba_fqnd should be resolved to backnet IP from OA MN!
        """
        return self.register_shared_node(backnet, login, password, frontnet,
            role='BSS Application', role_params={'billing.ui.host': ba_fqnd})

    def register_store(self, backnet, login, password, frontnet, new_hostname=None):
        """Register LINBAOS server

        :returns: host_id
        """
        return self.register_shared_node(backnet, login, password, frontnet,
            new_hostname, role='BSS Online Store')

    def get_ip_pool(self, name):
        """Get IP pool from database
        
        :returns: pool_id
        """
        con = uSysDB.connect()
        cur = con.cursor()
        cur.execute("SELECT pool_id, pool_name FROM ip_pools")
        pools = cur.fetchall()
        con.close()
        for pool in pools:
            if name == pool[1]:
                return pool[0]
        return None

    def create_ip_pool(self, name, start, end, mask, purpose):
        """Create IP pool

        Reenterable
        :returns: pool_id
        """
        # check if pools exists
        pool_id = self.get_ip_pool(name)
        if pool_id:
            return pool_id
        res = self.api_async_call_wait('pem.createIPPool',
            name=name, startIP=start, endIP=end, netmask=mask, purpose=purpose)
        return res.get('pool_id')

    def get_host_ips(self, host_id):
        """Get host IPs and NICs from database
        
        :returns: [[ip, if_id],..]
        """
        con = uSysDB.connect()
        cur = con.cursor()
        cur.execute("""SELECT ip_address, if_id
            FROM configured_ips
            WHERE host_id = %s""",
            (host_id,))
        ip0_ifs = cur.fetchall()
        con.close()
        # strip leading 0s from octets
        # 010 -> 10
        # 000 -> 0 !! The last zero should stay!
        ip_ifs = []
        for ip0, if_id in ip0_ifs:
            ip = '.'.join([ o0.lstrip('0') or '0' for o0 in ip0.split('.')])
            ip_ifs.append([ip, if_id])
        return ip_ifs

    def find_ip_nic(self, host_id, ip):
        """Find NIC which has ip assigned
        
        :returns: if_id
        """
        for if_ip, if_id in self.get_host_ips(host_id):
            if ip == if_ip:
                return if_id
        return None

    def bind_ip_pool(self, host_id, if_ip, pool_id):
        """Attach IP pool to NIC with specific ip

        Reenterable
        :raises OSAError: if IP is not found
        """
        if_id = self.find_ip_nic(host_id, if_ip)
        if not if_id:
            raise OSAError("Cannot find ip {0} on host, id: {1}"
                .format(if_ip, host_id))
        try:
            res = self.api_async_call_wait('pem.bindIPPool',
                pool_id=pool_id, interface_id=if_id)
        except OpenAPIError as err:
            # already attached?
            if (err.module_id == 'IPManager' and err.extype_id == 54 and
                err.properties['pool_id'] == str(pool_id)):
                return
            else:
                raise

    def find_brand(self, account_id, domain):
        """Find brand

        :returns: brand id
        """
        res = self.api_async_call_wait('pem.getVendorBrands',
            account_id=account_id)
        for brand in res:
            if brand['domain_name'] == domain:
                return brand['brand_id']
        return None

    def create_prov_brand(self, domain, exclusive_ip=False):
        if exclusive_ip:
            brand_id = self.api_async_call_wait('pem.brandDomain',domain_name=domain,ip_type='exclusive')
        else:
            brand_id = self.api_async_call_wait('pem.brandDomain',domain_name=domain,ip_type='shared')
        return brand_id

# if modeline is not enabled, run 'set modeline | doautocmd BufRead' in vim
# vim: tabstop=4:softtabstop=4:shiftwidth=4:textwidth=100:expandtab:autoindent:fileformat=unix
