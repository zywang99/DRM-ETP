import random
from DRMETP8nodes import mainDRMETP8
from DRMETP16nodes import mainDRMETP16
from TeleDTP8nodes import mainTELEDTP8
from TeleDTP16nodes import mainTELEDTP16

#设置8节点路径信息
mc_list8nodes = []
rate_list8nodes = []
linknum = 7
for i in range(linknum):
    mc_list8nodes.append(random.randint(20,50))
nodenum=8
for i in range(nodenum):
    rate_list8nodes.append(random.randint(20,50))

#设置16节点路径信息
mc_list16nodes = []
rate_list16nodes = []
linknum = 15
for i in range(linknum):
    mc_list16nodes.append(random.randint(20,50))
nodenum=16
for i in range(nodenum):
    rate_list16nodes.append(random.randint(20,50))

#运行协议
print("DRMETP runs in 8nodes path!")
mainDRMETP8(mc_list8nodes,rate_list8nodes)
print("TeleDTP runs in 8nodes path!")
mainTELEDTP8(mc_list8nodes,rate_list8nodes)
print("DRMETP runs in 16nodes path!")
mainDRMETP16(mc_list16nodes,rate_list16nodes)
print("TeleDTP runs in 16nodes path!")
mainTELEDTP16(mc_list16nodes,rate_list16nodes)