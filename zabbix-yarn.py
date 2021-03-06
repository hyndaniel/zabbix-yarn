from __future__ import division
import socket
import requests
from zabbix_sender.ZabbixPacket import ZabbixPacket
from zabbix_sender.ZabbixSender import ZabbixSender
from netifaces import interfaces, ifaddresses, AF_INET
from yarn_api_client import ApplicationMaster, HistoryServer, NodeManager, ResourceManager

# JMX_ADDR= 'http://XXXXXXXX:8088/jmx'
ZABBIX_ADDR = '192.168.1.35'
ZABBIX_PORT = '10051'
RM_ADDR = ('hadoop1','hadoop2')
#RM_ADDR = ('BIGL1TMP','BIGL2TMP')

class ZabbixHadoop:
    def __init__(self, zaddr=ZABBIX_ADDR,zport=ZABBIX_PORT,iface=None):
        self._API_TYPE = {
            1: {
                'API_ID': 'clusterInfo',
                'API_PREFIX': 'RM',
                'API_ADDRESS': 'http://RMADDRESS:8088/ws/v1/cluster/info',
                'KEY_PREFIX': 'Info'
            },
            2: {
                'API_ID': 'clusterMetrics',
                'API_PREFIX': 'RM',
                'API_ADDRESS': 'http://RMADDRESS:8088/ws/v1/cluster/metrics',
                'KEY_PREFIX': 'Metrics'
            },
            3:{
                'API_ID': 'scheduler',
                'API_PREFIX': 'RM',
                'API_ADDRESS': 'http://RMADDRESS:8088/ws/v1/cluster/scheduler',
                'KEY_PREFIX': 'Scheduler'
            },
            4:{
                'API_ID': 'apps',
                'API_PREFIX': 'RM',
                'API_ADDRESS': 'http://RMADDRESS:8088/ws/v1/cluster/apps',
                'KEY_PREFIX': 'Apps'
            },
            5: {
                'API_ID':'appStatInfo',
                'API_PREFIX':'RM',
                'API_ADDRESS':'http://RMADDRESS:8088/ws/v1/cluster/appstatistics',
                'KEY_PREFIX':'AppStatInfo'
            },
            6: {
                'API_ID':'nodes',
                'API_PREFIX':'RM',
                'API_ADDRESS':'http://RMADDRESS:8088/ws/v1/cluster/nodes',
                'KEY_PREFIX':'Nodes'
            },
        }
        self._type = 1
        self._activerm = self._get_activerm()
        # self.apitype= apitype
        self.zaddr = zaddr
        self.zport = zport
        self.ret_result = []
        self.final_result_dict ={}
        self.zbserver = ZabbixSender(zaddr, zport)
        self._ip = self._getLocalIP(iface)
        self.rm = ResourceManager(address=self._activerm,timeout=10)

    def _getLocalIP(self,iface):
        for i in interfaces():
            if i == iface:
                return ifaddresses(i)[2][0]['addr']

    def collect_app_stats(self, state_list=None, type_list=None):
        self._type = 5
        self.final_result_dict ={}
        self.ret_result= self.rm.cluster_application_statistics(state_list=state_list, application_type_list=state_list).data[
            self._API_TYPE[self._type]['API_ID']
        ]['statItem']

        for i in self.ret_result:
            self.final_result_dict[i['state']] = i['count']
        if len(self.final_result_dict) != 0:
            self._send_zabbix()
    def colletc_app_metric(self,state=None, final_status=None,
                           user=None, queue=None, limit=None,
                           started_time_begin=None, started_time_end=None,
                           finished_time_begin=None, finished_time_end=None):
        self._type = 4
        self.final_result_dict ={}
        self.ret_result = self.rm.cluster_applications(state=None, final_status=None,
                                                       user=None, queue=None, limit=None,
                                                       started_time_begin=None, started_time_end=None,
                                                       finished_time_begin=None, finished_time_end=None).data[
            self._API_TYPE[self._type]['API_ID']
        ]['app']
        for i in self.ret_result:
            if i['finalStatus']==u'FAILED' or i['finalStatus']==u'KILLED' :
                if self.final_result_dict.has_key(i['finalStatus']):
                    self.final_result_dict[i['finalStatus']] = '%s, %s:%s:%s' % (self.final_result_dict[i['finalStatus']], i['user'],i['name'],i['queue'])
                else:
                    self.final_result_dict[i['finalStatus']] = '%s:%s:%s' % (i['user'],i['name'],i['queue'])
        if len(self.final_result_dict) != 0:
            self._send_zabbix()

    def collect_cluster_metrics(self):
        self._type = 2
        self.final_result_dict = {}
        self.ret_result = self.rm.cluster_metrics().data[
            self._API_TYPE[self._type]['API_ID']
        ]
        self.final_result_dict['mem_usage'] = self.ret_result['allocatedMB']/self.ret_result['totalMB']
        self.final_result_dict['vcore_usage'] = self.ret_result['allocatedVirtualCores']/self.ret_result['totalVirtualCores']
        self.final_result_dict['unhealthyNodes'] = self.ret_result['unhealthyNodes']
        if len(self.final_result_dict) != 0:
            self._send_zabbix()

    def collect_scheduler_metrics(self):
        self._type  = 3
        self.final_result_dict = {}
        self.ret_result = self.rm.cluster_scheduler().data[
            self._API_TYPE[self._type]['API_ID']
        ]['schedulerInfo']
        self.final_result_dict['root_used_capacity'] = self.ret_result['usedCapacity']
        for index,queue in enumerate(self.ret_result['queues']['queue']):
            self.final_result_dict['queue'+str(index)+'_load'] = queue['usedCapacity']
        if len(self.final_result_dict) != 0:
            self._send_zabbix()

    def _send_zabbix(self):
        packet = ZabbixPacket()
        for k,v in self.final_result_dict.iteritems():
            packet.add(self._API_TYPE[self._type]['API_PREFIX']+'_'+self._ip, self._API_TYPE[self._type]['KEY_PREFIX']+'['+k+']', v)
        return 0
        self.zbserver.send(packet)
        print self.zbserver.status

    def _get_activerm(self):
        for addr in RM_ADDR:
            ret_val = requests.get(self._API_TYPE[self._type]['API_ADDRESS'].replace('RMADDRESS',addr))
            if ret_val.status_code == 200:
                json_val = ret_val.json()[self._API_TYPE[self._type]['API_ID']]
                if json_val['haState'] == 'ACTIVE' and json_val['state'] == 'STARTED':
                    return  addr

if __name__ == '__main__':
    #For Cluster Metrics
    zh = ZabbixHadoop(iface='{9FBE9029-B06C-4657-992E-15A0F04CD21D}')
    # zh.collect_app_stat(['running'])
    zh.collect_app_stats(type_list=['spark'])
    zh.colletc_app_metric()
    zh.collect_cluster_metrics()
    zh.collect_scheduler_metrics()



