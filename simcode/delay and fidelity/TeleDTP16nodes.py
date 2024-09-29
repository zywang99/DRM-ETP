import sys
sys.path.append("C:\\Users\\USTC\\Desktop\\Simulation")
from qns.entity.cchannel.cchannel import (ClassicChannel, ClassicPacket,
                                          RecvClassicPacket)
from qns.entity.memory.memory import QuantumMemory
from qns.entity.node.app import Application
from qns.entity.node.node import QNode
from qns.network.network import QuantumNetwork
from qns.network.route.dijkstra import DijkstraRouteAlgorithm
from qns.network.topology.linetopo import LineTopology
from qns.network.topology.topo import ClassicTopology
from qns.simulator.event import Event, func_to_event
from qns.simulator.simulator import Simulator
from entanglement_gen_swap import EntanglementGenerationAndSwapping
import xlwt
import math


#源端发送信息包，信息包含有路径信息：Tele-DTP方案
class SendApp(Application):
    def __init__(self, dest: QNode, routelist: list, send_rate:float):
        super().__init__()
        self.dest = dest
        #包含了路径上的节点信息（按序）
        self.routelist = routelist
        self.send_rate = send_rate

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        t = simulator.ts
        event = func_to_event(t, self.send_packet, by=self)
        self._simulator.add_event(event)

    def send_packet(self):
        if len(self.routelist) == 0 :
            print("not found next hop")
        next_hop_name = self.routelist[1]
        packet = ClassicPacket(msg={"cmd":"forward","routelist":self.routelist,"CE":"前向包","W":self.get_node().w}, src=self.get_node(), dest=self.dest)
        for next_node in self.get_node().adjnode:
            if next_node.name == next_hop_name:
                cchannel: ClassicChannel = self.get_node().get_cchannel(next_node)
                if cchannel is None:
                    print("not found next channel")
                # send the classic packet
                cchannel.send(packet=packet, next_hop=next_node)
            # calculate the next sending time,按照我们的时隙长度send_rate来发送
        t = self._simulator.current_time + \
            self._simulator.time(sec=1 / self.send_rate)
        # insert the next send event to the simulator
        event = func_to_event(t, self.send_packet, by=self)
        self._simulator.add_event(event)
                

#其他节点处理信息包
class ClassicPacketForwardApp(Application):
    """
    This application will generate routing table for classic networks
    and allow nodes to forward classic packats to the destination.
    """
    def __init__(self):
        """
        Args:
            route (RouteImpl): a route implement
        """
        super().__init__()
        self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [])

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)

    def handleClassicPacket(self, self_node:QNode,event: Event):
        packet = event.packet
        self_node: QNode = self.get_node()
        msg = packet.get()
        cmd = msg["cmd"]
        routelist:list = msg["routelist"]
        w = msg["W"]
        CE = msg["CE"]
        src = packet.src
        dst = packet.dest
        #到达了目的节点
        if dst == self_node:
            if cmd == "forward":
                # 收到消息后，计算完成后，触发反向的存储锁定过程。
                #计算最小速率
                if len(routelist) == 0 :
                    print("not found next hop")
                next_hop_name = routelist[-2]
                if (dst.name,src.name) not in self.get_node().requests:
                    self.get_node().requests.append((dst.name,src.name))
                for next_node in self_node.adjnode:
                    if next_node.name == next_hop_name:
                        for memory in self.get_node().memories:
                            #把该请求加入请求队列
                            #存储锁定
                            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                                #添加存储中的请求信息，列表信息为容量
                                if memory.capacity >= w:
                                    units = w
                                    CE = 0
                                else:
                                    units = min(math.ceil(w/2),memory.capacity)
                                    CE = 1
                                #两个节点的存储添加请求信息
                                memory.requests[(dst.name,src.name)] = units
                                #按照需求升序排序
                                requests_sorted = sorted(memory.requests.items(), key=lambda x: x[1], reverse=False)
                                #重新构造请求需求和剩余容量
                                memory.requests = {}
                                memory.remain = memory.capacity
                                next_node.get_memory(memory.name).requests = {}
                                next_node.get_memory(memory.name).remain = memory.capacity
                                for i, request_unit in enumerate(requests_sorted):
                                    memory.requests[request_unit[0]] = min(request_unit[1],memory.remain)
                                    next_node.get_memory(memory.name).requests[request_unit[0]] = min(request_unit[1],next_node.get_memory(memory.name).remain)
                                    memory.remain -=  min(request_unit[1],memory.remain)
                                    next_node.get_memory(memory.name).remain -=  min(request_unit[1],next_node.get_memory(memory.name).remain)
                                #更新经过该存储的全部存储占用信息
                                index = 0 #当前的分配截至索引信息
                                for request in memory.requests.keys():
                                    units = memory.requests[request]
                                    #如果字典为空，则创建相应字典
                                    if request not in self.get_node().req_mem.keys():
                                        self.get_node().req_mem[request] = []
                                        next_node.req_mem[request] = []
                                        self.get_node().req_mem[request].append([memory.name,index,index+units])
                                        next_node.req_mem[request].append([memory.name,index,index+units])  
                                    else:
                                        for info_list in self.get_node().req_mem[request]:
                                            #已经有该存储信息，则直接用新的信息覆盖
                                            if memory.name in info_list:
                                                idx = self.get_node().req_mem[request].index(info_list)
                                                self.get_node().req_mem[request][idx] = [memory.name,index,index+units]
                                                break
                                        for info_list in next_node.req_mem[request]:
                                            if memory.name in info_list:
                                                idx = next_node.req_mem[request].index(info_list)
                                                next_node.req_mem[request][idx] = [memory.name,index,index+units]
                                                break
                                    index = index+units
                        newpacket = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"CE":CE,"W":w}, src=packet.dest, dest=packet.src)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
                        if cchannel is None:
                            print("not found next channel")
                            return True
                        # send the classic packet
                        cchannel.send(packet=newpacket, next_hop=next_node)
                        return True

            if cmd == "backward":
                if (src.name,dst.name) not in self.get_node().requests:
                    self.get_node().requests.append((src.name,dst.name))
                if CE == 1:
                    self.get_node().w = math.ceil(w/2)
                    #拥塞避免状态
                    self.get_node().state = 1
                if self.get_node().state == 0:
                    self.get_node().w *= 2
                else:
                    self.get_node().w += 1
                return True
        #没到目的节点
        else:
            # If destination is not this node, forward this packet
            if cmd == "forward":
                idx = routelist.index(self_node.name)
                next_hop_name = routelist[idx+1]
                for next_node in self_node.adjnode:
                    if next_node.name == next_hop_name:
                        cchannel: ClassicChannel = self.get_node().get_cchannel(next_node)
                        packet = ClassicPacket(msg={"cmd":"forward","routelist":routelist,"CE":CE,"W":w}, src=src, dest=dst)
                        if cchannel is None:
                            print("not found next channel")
                            return True
                        # send the classic packet
                        cchannel.send(packet=packet, next_hop=next_node)
                        return True
            if cmd == "backward":
                idx = routelist.index(self_node.name)
                next_hop_name = routelist[idx-1]
                for next_node in self_node.adjnode:
                    if next_node.name == next_hop_name:
                        if (src.name,dst.name) not in self.get_node().requests:
                            self.get_node().requests.append((src.name,dst.name))
                        #存储锁定
                        for memory in self.get_node().memories:
                            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                                # 计算锁定存储数量
                                if memory.capacity >= w and CE == 0:
                                    units = w
                                else:
                                    units = min(math.ceil(w/2),memory.capacity)
                                    CE = 1
                                memory.requests[(src.name,dst.name)] = units
                                #按照需求升序排序
                                requests_sorted = sorted(memory.requests.items(), key=lambda x: x[1], reverse=False)
                                #重新构造请求需求和剩余容量
                                memory.requests = {}
                                memory.remain = memory.capacity
                                next_node.get_memory(memory.name).requests = {}
                                next_node.get_memory(memory.name).remain = memory.capacity
                                for i, request_unit in enumerate(requests_sorted):
                                    memory.requests[request_unit[0]] = min(request_unit[1],memory.remain)
                                    next_node.get_memory(memory.name).requests[request_unit[0]] = min(request_unit[1],next_node.get_memory(memory.name).remain)
                                    memory.remain -=  min(request_unit[1],memory.remain)
                                    next_node.get_memory(memory.name).remain -=  min(request_unit[1],next_node.get_memory(memory.name).remain)
                                #更新经过该存储的全部存储占用信息
                                index = 0 #当前的分配截至索引信息
                                for request in memory.requests.keys():
                                    units = memory.requests[request]
                                    if request not in self.get_node().req_mem.keys():
                                        self.get_node().req_mem[request] = []
                                        self.get_node().req_mem[request].append([memory.name,index,index+units])
                                    else:
                                        flag = 0
                                        for info_list in self.get_node().req_mem[request]:
                                            #已经有该存储信息，则直接用新的信息覆盖
                                            if memory.name in info_list:
                                                idx = self.get_node().req_mem[request].index(info_list)
                                                self.get_node().req_mem[request][idx] = [memory.name,index,index+units]
                                                flag = 1
                                                break
                                            else:
                                                continue
                                        if flag == 0:
                                            self.get_node().req_mem[request].append([memory.name,index,index+units])
                                    if request not in next_node.req_mem.keys():
                                        next_node.req_mem[request] = []
                                        next_node.req_mem[request].append([memory.name,index,index+units])
                                    else:
                                        flag = 0
                                        for info_list in next_node.req_mem[request]:
                                            if memory.name in info_list:
                                                idx = next_node.req_mem[request].index(info_list)
                                                next_node.req_mem[request][idx] = [memory.name,index,index+units]
                                                flag = 1
                                                break
                                            else:
                                                continue
                                        if flag == 0:
                                            next_node.req_mem[(src.name,dst.name)].append([memory.name,index,index+units])
                                    index = index+units    
                        cchannel: ClassicChannel = self.get_node().get_cchannel(next_node)
                        packet = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"CE":CE,"W":w}, src=src, dest=dst)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
                        if cchannel is None:
                            print("not found next channel")
                            return True
                        # send the classic packet
                        cchannel.send(packet=packet, next_hop=next_node)
                        return True


def mainTELEDTP16(mc_list,rate_list):
    #w为了获得足量的数据点，运行时间拉长
    s = Simulator(0, 1000, accuracy=10000000)
    topo = LineTopology(nodes_number=16,
                            qchannel_args={"delay": 0},
                            cchannel_args={"delay": 0})

    net = QuantumNetwork(topo=topo, classic_topo=ClassicTopology.All,route=DijkstraRouteAlgorithm())
    # build quantum routing table
    net.build_route()
    #构建相邻节点信息和添加存储
    All_link = []
    idx= 0
    for node in net.nodes:
        node.genrate = rate_list[idx]
        idx+=1
        for qchannel in node.qchannels:
            All_link.append(qchannel.node_list)
            #删除掉其中的重复项
            All_link = [i for n, i in enumerate(All_link) if i not in All_link[:n]]
    idx = 0 
    for link in All_link:
        n1: QNode = link[0]
        n2: QNode = link[1]
        if n2 not in n1.adjnode:
            n1.adjnode.append(n2)
        if n1 not in n2.adjnode:
            n2.adjnode.append(n1)
        #随机生成每块存储的容量
        n1.add_memory(QuantumMemory(n1.name+"~"+n2.name,n1,mc_list[idx],n1.genrate+n2.genrate,0))
        n2.add_memory(QuantumMemory(n1.name+"~"+n2.name,n2,mc_list[idx],n1.genrate+n2.genrate,0))
        idx+=1

    #为所有节点添加APP
    for n in net.nodes:
        #改写前向转发APP，让其具备添加本地信息的能力
        n.add_apps(ClassicPacketForwardApp())
        n.add_apps(EntanglementGenerationAndSwapping())
    src = net.get_node("n1")
    dst = net.get_node("n16")
    list = net.query_route(src,dst)[0][2]         
    routelist = []
    for node in list:
        routelist.append(node.name)
    src.add_apps(SendApp(dst, routelist,send_rate=1))
    #运行仿真
    net.install(s)
    s.run()
    book = xlwt.Workbook(encoding='utf-8')
    # 在excel表格类型文件中建立一张sheet表单
    sheet = book.add_sheet('sheet1')
    for node in net.nodes:
        print(node.name+": "+str(node.EDR))
    i = 0
    for delay in src.delay:
        sheet.write(i, 0, float(str(delay)))
        i+=1

    j = 0
    for fidelity in src.fidelity:
        sheet.write(j, 1, float(str(fidelity)))
        j+=1
    book.save("delayandfidelity_TELEDTP16.xls")