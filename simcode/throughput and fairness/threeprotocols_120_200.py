import sys
sys.path.append("C:\\Users\\USTC\\Desktop\\Simulation")
import math
import random
from entanglement_gen_swap import EntanglementGenerationAndSwapping
from qns.entity.cchannel.cchannel import (ClassicChannel, ClassicPacket,
                                         RecvClassicPacket)
from qns.entity.memory.memory import QuantumMemory
from qns.entity.node.app import Application
from qns.entity.node.node import QNode
from qns.network.network import QuantumNetwork
from qns.network.route.dijkstra import DijkstraRouteAlgorithm
from qns.network.topology import RandomTopology
from qns.network.topology.topo import ClassicTopology
from qns.simulator.event import Event, func_to_event
from qns.simulator.simulator import Simulator

#源端发送信息包，信息包含有路径信息:DRM-ETP
class SendApp1(Application):
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
        #填充第一跳空闲容量
        for memory in self.get_node().memories:
            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                #请求第一次来
                if (self.dest.name,self.get_node().name) not in self.get_node().req_mem.keys():
                    #将经过该存储的请求数加1，以便求出阈值
                    memory.requestnum +=1
                    threshold:float= memory.capacity/memory.requestnum
                    #包含max值，纠缠生成速率比值
                    sign = (max(threshold,memory.remain),memory.rate/memory.capacity)
                    for next_node in self.get_node().adjnode:
                        if next_node.name == next_hop_name:
                            next_node.get_memory(memory.name).requestnum +=1
                #请求不是第一次来
                else:
                    threshold:float= memory.capacity/memory.requestnum
                    for info_list in self.get_node().req_mem[(self.dest.name,self.get_node().name)]:
                        if memory.name in info_list:
                            #max值，纠缠生成速率比值
                            sign = (max(threshold,memory.remain+info_list[2]-info_list[1]),memory.rate/memory.capacity)
        packet = ClassicPacket(msg={"cmd":"forward","routelist":self.routelist,"capcaity":[sign]}, src=self.get_node(), dest=self.dest)
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
class ClassicPacketForwardApp1(Application):
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
        capcaity = msg["capcaity"]
        src = packet.src
        dst = packet.dest
        #到达了目的节点
        if dst == self_node:
            if cmd == "forward":
                # 收到消息后，计算完成后，触发反向的存储锁定过程。
                #计算最小速率
                min_rate = 1000
                for sign in capcaity:
                    if (sign[0])*sign[1] < min_rate:
                        min_rate = (sign[0])*sign[1]
                newpacket = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"capcaity":min_rate}, src=packet.dest, dest=packet.src)
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
                                units = math.ceil(min_rate/(memory.rate/memory.capacity))
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
                return True
            return False
        #没到目的节点
        else:
            # If destination is not this node, forward this packet
            if cmd == "forward":
                idx = routelist.index(self_node.name)
                next_hop_name = routelist[idx+1]
                for next_node in self_node.adjnode:
                    if next_node.name == next_hop_name:
                        cchannel: ClassicChannel = self.get_node().get_cchannel(next_node)
                        for memory in self.get_node().memories:
                            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                                if (dst.name,src.name) not in self.get_node().req_mem.keys():
                                    memory.requestnum += 1
                                    threshold:float = memory.capacity/memory.requestnum
                                    sign = (max(threshold,memory.remain),memory.rate/memory.capacity)
                                    next_node.get_memory(memory.name).requestnum +=1
                                else:
                                    threshold:float = memory.capacity/memory.requestnum
                                    for info_list in self.get_node().req_mem[(dst.name,src.name)]:
                                        if memory.name in info_list:
                                            #已占用容量，剩余容量，纠缠生成速率
                                            sign = (max(threshold,memory.remain+info_list[2]-info_list[1]),memory.rate/memory.capacity)
                                capcaity.append(sign)
                        packet = ClassicPacket(msg={"cmd":"forward","routelist":routelist,"capcaity":capcaity}, src=src, dest=dst)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
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
                                units = math.ceil(capcaity/(memory.rate/memory.capacity))
                                #两个节点的存储添加请求信息
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
                                # #更新经过该存储的全部存储占用信息
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
                        packet = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"capcaity":capcaity}, src=src, dest=dst)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
                        if cchannel is None:
                            print("not found next channel")
                            return True
                        # send the classic packet
                        cchannel.send(packet=packet, next_hop=next_node)
                        return True


#源端发送信息包，信息包含有路径信息:SA-ETP
class SendApp2(Application):
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
        #填充第一跳空闲容量
        for memory in self.get_node().memories:
            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                #请求第一次来
                if (self.dest.name,self.get_node().name) not in self.get_node().req_mem.keys():
                    #将经过该存储的请求数加1，以便求出阈值
                    memory.requestnum +=1
                    threshold:float= memory.capacity/memory.requestnum
                    #包含max值，纠缠生成速率比值
                    sign = (threshold,memory.rate/memory.capacity)
                    # memory.remain -= threshold
                    for next_node in self.get_node().adjnode:
                        if next_node.name == next_hop_name:
                            next_node.get_memory(memory.name).requestnum +=1
                #请求不是第一次来
                else:
                    threshold:float= memory.capacity/memory.requestnum
                    for info_list in self.get_node().req_mem[(self.dest.name,self.get_node().name)]:
                        if memory.name in info_list:
                            #max值，纠缠生成速率比值
                            sign = (threshold,memory.rate/memory.capacity)
                            # memory.remain -= threshold
        packet = ClassicPacket(msg={"cmd":"forward","routelist":self.routelist,"capcaity":[sign]}, src=self.get_node(), dest=self.dest)
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
class ClassicPacketForwardApp2(Application):
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
        capcaity = msg["capcaity"]
        src = packet.src
        dst = packet.dest
        #到达了目的节点
        if dst == self_node:
            if cmd == "forward":
                # 收到消息后，计算完成后，触发反向的存储锁定过程。
                #计算最小速率
                min_rate = 1000
                for sign in capcaity:
                    if (sign[0])*sign[1] < min_rate:
                        min_rate = (sign[0])*sign[1]
                newpacket = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"capcaity":min_rate}, src=packet.dest, dest=packet.src)
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
                                units = math.ceil(min_rate/(memory.rate/memory.capacity))
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
                return True
            return False
        #没到目的节点
        else:
            # If destination is not this node, forward this packet
            if cmd == "forward":
                idx = routelist.index(self_node.name)
                next_hop_name = routelist[idx+1]
                for next_node in self_node.adjnode:
                    if next_node.name == next_hop_name:
                        cchannel: ClassicChannel = self.get_node().get_cchannel(next_node)
                        for memory in self.get_node().memories:
                            if memory.name == self.get_node().name+"~"+next_hop_name or memory.name == next_hop_name + "~"+self.get_node().name:
                                if (dst.name,src.name) not in self.get_node().req_mem.keys():
                                    memory.requestnum += 1
                                    threshold:float = memory.capacity/memory.requestnum
                                    sign = (threshold,memory.rate/memory.capacity)
                                    next_node.get_memory(memory.name).requestnum +=1
                                else:
                                    threshold:float = memory.capacity/memory.requestnum
                                    for info_list in self.get_node().req_mem[(dst.name,src.name)]:
                                        if memory.name in info_list:
                                            #已占用容量，剩余容量，纠缠生成速率
                                            sign = (threshold,memory.rate/memory.capacity)
                                capcaity.append(sign)
                        packet = ClassicPacket(msg={"cmd":"forward","routelist":routelist,"capcaity":capcaity}, src=src, dest=dst)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
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
                                units = math.floor(capcaity/(memory.rate/memory.capacity))
                                #两个节点的存储添加请求信息
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
                        packet = ClassicPacket(msg={"cmd":"backward","routelist":routelist,"capcaity":capcaity}, src=src, dest=dst)
                        cchannel: ClassicChannel = self_node.get_cchannel(next_node)
                        if cchannel is None:
                            print("not found next channel")
                            return True
                        # send the classic packet
                        cchannel.send(packet=packet, next_hop=next_node)
                        return True

#源端发送信息包，信息包含有路径信息:Tele-DTP
class SendApp3(Application):
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
class ClassicPacketForwardApp3(Application):
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
                    
def main1(request_list:list,seed:int,mc_list:list,rate_list:list):
    from qns.utils.rnd import set_seed
    set_seed(seed)
    s = Simulator(0, 50, accuracy=10000000)
    topo = RandomTopology(nodes_number = 120,
                          lines_number = 200,
                        qchannel_args={"delay": 0},
                              cchannel_args={"delay": 0},
                              nodes_apps=[])
    net = QuantumNetwork(topo=topo, classic_topo=ClassicTopology.All,route=DijkstraRouteAlgorithm())
    # build quantum routing table
    net.build_route()
    #构建相邻节点信息和添加存储
    All_link = []
    idx= 0
    for node in net.nodes:
        # print(len(rate_list))
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
        n.add_apps(ClassicPacketForwardApp1())
        n.add_apps(EntanglementGenerationAndSwapping())
    

      #构建请求
    src_list = []
    for request in request_list:
        src = net.get_node(request[0])
        dst = net.get_node(request[1])
        list = net.query_route(src,dst)[0][2]
        src_list.append((src,len(list)))
        routelist = []
        for node in list:
            routelist.append(node.name)
        src.add_apps(SendApp1(dst, routelist,send_rate=1))
                        
    #运行仿真
    net.install(s)
    s.run()

    min_EDR = 100000000
    EDR = 0
    EDR_list = []
    for tuple in src_list:
        node = tuple[0]
        hop = tuple[1]-2
        EDR += node.EDR*pow(0.8,hop)
        EDR_list.append(node.EDR*pow(0.8,hop))
        if node.EDR < min_EDR:
            min_EDR = node.EDR
    #求公平
    sum = 0
    sum_pingfang = 0
    for e in EDR_list:
        sum += e
        sum_pingfang += e*e
    jain = sum *sum /(len(request_list)*sum_pingfang)
    print("请求"+str(len(request_list))+"个：" + str(EDR/50)+" jain:"+ str(jain))
    return EDR/50,jain,min_EDR/50




def main2(request_list:list,seed:int,mc_list:list,rate_list:list):
    from qns.utils.rnd import set_seed
    set_seed(seed)
    s = Simulator(0, 50, accuracy=10000000)
    topo = RandomTopology(nodes_number = 120,
                          lines_number = 200,
                        qchannel_args={"delay": 0},
                              cchannel_args={"delay": 0},
                              nodes_apps=[])
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
        n.add_apps(ClassicPacketForwardApp2())
        n.add_apps(EntanglementGenerationAndSwapping())
        
      #构建请求
    src_list = []
    for request in request_list:
        src = net.get_node(request[0])
        dst = net.get_node(request[1])
        list = net.query_route(src,dst)[0][2]
        src_list.append((src,len(list)))
        routelist = []
        for node in list:
            routelist.append(node.name)
        src.add_apps(SendApp2(dst, routelist,send_rate=1))
                        
    #运行仿真
    net.install(s)
    s.run()

    min_EDR = 100000000
    EDR = 0
    EDR_list = []
    for tuple in src_list:
        node = tuple[0]
        hop = tuple[1]-2
        EDR += node.EDR*pow(0.8,hop)
        EDR_list.append(node.EDR*pow(0.8,hop))
        if node.EDR < min_EDR:
            min_EDR = node.EDR
    #求公平
    sum = 0
    sum_pingfang = 0
    for e in EDR_list:
        sum += e
        sum_pingfang += e*e
    jain = sum *sum /(len(request_list)*sum_pingfang)
    print("请求"+str(len(request_list))+"个：" + str(EDR/50)+" jain:"+ str(jain))
    return EDR/50,jain,min_EDR/50

def main3(request_list:list,seed:int,mc_list:list,rate_list:list):
    from qns.utils.rnd import set_seed
    set_seed(seed)
    s = Simulator(0, 50, accuracy=10000000)
    topo = RandomTopology(nodes_number = 120,
                          lines_number = 200,
                        qchannel_args={"delay": 0},
                              cchannel_args={"delay": 0},
                              nodes_apps=[])
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
        n.add_apps(ClassicPacketForwardApp3())
        n.add_apps(EntanglementGenerationAndSwapping())
        
      #构建请求
    src_list = []
    for request in request_list:
        src = net.get_node(request[0])
        dst = net.get_node(request[1])
        list = net.query_route(src,dst)[0][2]
        src_list.append((src,len(list)))
        routelist = []
        for node in list:
            routelist.append(node.name)
        src.add_apps(SendApp3(dst, routelist,send_rate=1))
                        
    #运行仿真
    net.install(s)
    s.run()

    min_EDR = 100000000
    EDR = 0
    EDR_list = []
    for tuple in src_list:
        node = tuple[0]
        hop = tuple[1]-2
        EDR += node.EDR*pow(0.8,hop)
        EDR_list.append(node.EDR*pow(0.8,hop))
        if node.EDR < min_EDR:
            min_EDR = node.EDR
    #求公平
    sum = 0
    sum_pingfang = 0
    for e in EDR_list:
        sum += e
        sum_pingfang += e*e
    jain = sum *sum /(len(request_list)*sum_pingfang)
    print("请求"+str(len(request_list))+"个：" + str(EDR/50)+" jain:"+ str(jain))
    return EDR/50,jain,min_EDR/50

def main(request_num:int,seed:int):
    from qns.utils.rnd import set_seed
    set_seed(seed)
    topo = RandomTopology(nodes_number = 120,
                          lines_number = 200,
                        qchannel_args={"delay": 0},
                              cchannel_args={"delay": 0},
                              nodes_apps=[])
    net = QuantumNetwork(topo=topo, classic_topo=ClassicTopology.All,route=DijkstraRouteAlgorithm())
    net.build_route()
    nodelist = []
    #为所有节点添加APP
    for n in net.nodes:
        nodelist.append(n)
      #构建请求
    request_list = []
    find = 0
    while (find < request_num):
        i = random.randint(0,len(nodelist)-1)
        j = random.randint(0,len(nodelist)-1)
        if i != j:
            src = nodelist[i]
            dst = nodelist[j]
            list = net.query_route(src,dst)[0][2]
            if len(list) >= 3:
                request_list.append((src.name,dst.name))
                nodelist.remove(src)
                nodelist.remove(dst)
                find += 1
            else:
                continue
    return request_list

if __name__ == "__main__":
    #创建随机数种子列表
    round = 100
    seed_list = []
    mc_list = []
    rate_list = []
    for i in range(round):
        seed_list.append(random.randint(0,500))
    linknum = 200
    for i in range(linknum):
        mc_list.append(random.randint(20,50))
    nodenum = 120
    for i in range(nodenum):
        rate_list.append(random.randint(20,50))

    #记录数据
    EDR_list1 = [0]*8
    jain_list1 = [0]*8
    min_EDR1_list1 = [0]*8
    EDR_list2 = [0]*8
    jain_list2 = [0]*8
    min_EDR2_list2 = [0]*8
    EDR_list3 = [0]*8
    jain_list3 = [0]*8
    min_EDR3_list3 = [0]*8

    k = 0
    while (k < round):
        k += 1
        for i in range (20,35,2):
            request_list = main(i,seed_list[k-1])
            print(request_list)
            EDR1,jain1,min_EDR1 = main1(request_list,seed_list[k-1],mc_list,rate_list)
            EDR2,jain2,min_EDR2 = main2(request_list,seed_list[k-1],mc_list,rate_list)
            EDR3,jain3,min_EDR3 = main3(request_list,seed_list[k-1],mc_list,rate_list)
            EDR_list1[int(i/2-10)] += EDR1
            jain_list1[int(i/2-10)] += jain1
            min_EDR1_list1[int(i/2-10)] += min_EDR1
            EDR_list2[int(i/2-10)] += EDR2
            jain_list2[int(i/2-10)] += jain2
            min_EDR2_list2[int(i/2-10)] += min_EDR2
            EDR_list3[int(i/2-10)] += EDR3
            jain_list3[int(i/2-10)] += jain3
            min_EDR3_list3[int(i/2-10)] += min_EDR3
    # 收集数据
    import xlwt
    book = xlwt.Workbook(encoding='utf-8')
    # 在excel表格类型文件中建立一张sheet表单
    sheet = book.add_sheet('sheet1')
    idx = 0
    while(idx < 8):
        sheet.write(idx, 0, EDR_list1[idx]/round)
        sheet.write(idx, 1, jain_list1[idx]/round)
        sheet.write(idx, 2, min_EDR1_list1[idx]/round)
        sheet.write(idx, 3, EDR_list2[idx]/round)
        sheet.write(idx, 4, jain_list2[idx]/round)
        sheet.write(idx, 5, min_EDR2_list2[idx]/round)
        sheet.write(idx, 6, EDR_list3[idx]/round)
        sheet.write(idx, 7, jain_list3[idx]/round)
        sheet.write(idx, 8, min_EDR3_list3[idx]/round)
        idx+=1
    
    book.save("result120200.xls")

    