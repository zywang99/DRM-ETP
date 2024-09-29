import sys
sys.path.append("C:\\Users\\USTC\\Desktop\\Simulation")
from qns.simulator.simulator import Simulator
from qns.entity.node.app import Application
from qns.entity.node.node import QNode
from qns.simulator.event import func_to_event
from qns.simulator.simulator import Simulator
from qns.models.epr.entanglement import BaseEntanglement
import random

#纠缠生成，交换app，加载到所有节点
class EntanglementGenerationAndSwapping(Application):
    def __init__(self):
        super().__init__()

    #概率函数
    def probability(self,p):
        if random.random() <= p:
            return True
        else:
            return False

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        self.own: QNode = node
        self.rate = 40
        t = simulator.ts
        event = func_to_event(t, self.link_generation, by=self)
        self._simulator.add_event(event)

    
    def link_generation(self):
        for n in self.own.adjnode:
            self.generate_epr(self.own,n)
        t = self._simulator.current_time + self._simulator.time(sec=1/self.rate)
        # insert the next send event to the simulator
        event = func_to_event(t, self.link_generation, by=self)
        self._simulator.add_event(event)
            
    #产生不受存储占用的限制,返回存放的索引信息
    def generate_epr(self, src: QNode, dst: QNode) :
        #找到正确的存储名
        mem_test1 = src.get_memory(src.name+"~"+dst.name)
        if mem_test1 !=None:
            m_name = src.name+"~"+dst.name
        else:
            m_name = dst.name+"~"+src.name
        m1 = src.get_memory(m_name)
        m2 = dst.get_memory(m_name)

        #求余运算
        idx = int(m1.gen_number % m1.capacity)
        m1.gen_number+=1
        m2.gen_number+=1
        t = self._simulator.tc.sec 
        #检查纠缠对是否超时，需要擦除
        for i in range(0,m1.capacity):
            if m1._storage[i]!= None and t - m1._storage[i].birthtime >= 1:
                localepr = m1._storage[i]
                localepr.othernode.get_memory(localepr.othermemname)._storage[localepr.otherindex] = None
                m1._storage[i] = None
            if m2._storage[i]!= None and t - m2._storage[i].birthtime >= 1:
                localepr = m2._storage[i]
                localepr.othernode.get_memory(localepr.othermemname)._storage[localepr.otherindex] = None
                m2._storage[i] = None

        #要么全为空，要么还没用，用新的覆盖
        if (m1._storage[idx] is not None and m2._storage[idx] is not None) or (m1._storage[idx] is None and m2._storage[idx] is None):
            if self.probability(m1.P):
                fidelity =  0.99
                epr1 = BaseEntanglement(fidelity=fidelity, thisindex=idx,otherindex=idx,thisnode=src,othernode=dst,thismemname = m_name,othermemname=m_name,name=src.name+"~"+dst.name+" "+str(self._simulator.tc),birthtime= t)
                epr2 = BaseEntanglement(fidelity=fidelity, thisindex=idx,otherindex=idx,thisnode=dst,othernode=src,thismemname = m_name,othermemname=m_name,name=src.name+"~"+dst.name+" "+str(self._simulator.tc),birthtime= t)
                #标记该纠缠的请求归属
                for request in m1.requests.keys():
                    for infolist in src.req_mem[request]:
                        if infolist[0] == m_name:
                            if idx >= infolist[1] and idx < infolist[2]:
                                epr1.request = request
                                epr2.request = request
                                src.allepr += 1
                                dst.allepr += 1
                                break
                #存储未被分配，分发到这些上的纠缠对无意义。
                if epr1.request == None:
                    del epr1
                    del epr2
                    return 0
                m1._storage[idx] = epr1
                m2._storage[idx] = epr2
                #遍历所有请求
                #第一：完成src端的纠缠匹配尝试
                for request in src.requests:
                    #得到每个请求的存储占用信息列表
                    info_list = src.req_mem[request]
                    if len(info_list) > 1:
                        for info in info_list:
                            if m_name == info[0] and epr1.request == request:
                                #说明该产生的新纠缠对被某个请求所占用，可以匹配执行纠缠交换
                                #寻找另一个存储
                                for info in info_list:
                                    #找到另外一个请求
                                    if m_name != info[0]:
                                        for idx2 in range(0,src.get_memory(info[0]).capacity):
                                            if src.get_memory(info[0])._storage[idx2] != None and src.get_memory(info[0])._storage[idx2].request == request:
                                                self.swapping(src,m_name,info[0],idx,idx2,request)
                                                return True
                                    else:
                                        continue
                           
                #第一：完成dst端的纠缠匹配尝试
                for request in dst.requests:
                    #得到每个请求的存储占用信息列表
                    info_list = dst.req_mem[request]
                    if len(info_list) > 1:
                        for info in info_list:
                            if m_name == info[0] and epr2.request == request:
                                #说明该产生的新纠缠对被某个请求所占用，可以匹配执行纠缠交换
                                #寻找另一个存储
                                for info in info_list:
                                    #找到另外一个存储
                                    if m_name != info[0]:
                                        for idx2 in range(0,dst.get_memory(info[0]).capacity):
                                            #找到一个就可以
                                            if dst.get_memory(info[0])._storage[idx2] != None and dst.get_memory(info[0])._storage[idx2].request == request:
                                                self.swapping(dst,m_name,info[0],idx,idx2,request)
                                                return True
                                    else:
                                        continue
            else:
                return None
        else:
            return None
       
    #节点执行纠缠交换
    def swapping(self,node:QNode,QM1_name:str,QM2_name:str,idx1:int,idx2:int,request:str):
        QM1 = node.get_memory(QM1_name)
        QM2 = node.get_memory(QM2_name)
        localepr1 = QM1._storage[idx1]
        localepr2 = QM2._storage[idx2]
        node.time.append(str(self._simulator.tc - localepr1.birthtime))
        node.time.append(str(self._simulator.tc - localepr2.birthtime))
        leftepr:BaseEntanglement = localepr1.othernode.get_memory(localepr1.othermemname)._storage[localepr1.otherindex]
        rightepr:BaseEntanglement = localepr2.othernode.get_memory(localepr2.othermemname)._storage[localepr2.otherindex]
        #赋予新纠缠对新的纠缠关系
        leftepr.othernode = localepr2.othernode
        leftepr.othermemname = localepr2.othermemname
        leftepr.otherindex = localepr2.otherindex
        rightepr.othernode = localepr1.othernode
        rightepr.othermemname = localepr1.othermemname
        rightepr.otherindex = localepr1.otherindex
        #擦除本地存储
        QM1._storage[idx1] = None
        QM2._storage[idx2] = None
        if leftepr.thisnode.name == request[0] and leftepr.othernode.name == request[1]:
            delay1 = self._simulator.tc - leftepr.thisnode.get_memory(leftepr.thismemname)._storage[leftepr.thisindex].birthtime
            delay2 = self._simulator.tc - rightepr.thisnode.get_memory(rightepr.thismemname)._storage[rightepr.thisindex].birthtime
            leftepr.thisnode.get_memory(leftepr.thismemname)._storage[leftepr.thisindex] = None
            rightepr.thisnode.get_memory(rightepr.thismemname)._storage[rightepr.thisindex] = None
            leftepr.othernode.EDR +=1
            leftepr.thisnode.EDR +=1
            leftepr.othernode.delay.append(max(delay1,delay2))
            leftepr.thisnode.delay.append(max(delay1,delay2))
            return True
        if leftepr.thisnode.name == request[1] and leftepr.othernode.name == request[0]:
            delay1 = self._simulator.tc - leftepr.thisnode.get_memory(leftepr.thismemname)._storage[leftepr.thisindex].birthtime
            delay2 = self._simulator.tc - rightepr.thisnode.get_memory(rightepr.thismemname)._storage[rightepr.thisindex].birthtime
            leftepr.thisnode.get_memory(leftepr.thismemname)._storage[leftepr.thisindex] = None
            rightepr.thisnode.get_memory(rightepr.thismemname)._storage[rightepr.thisindex] = None
            leftepr.thisnode.EDR += 1
            leftepr.othernode.EDR += 1
            leftepr.othernode.delay.append(max(delay1,delay2))
            leftepr.thisnode.delay.append(max(delay1,delay2))
            return True
        #判断是否可继续执行纠缠交换
        leftnode = leftepr.thisnode
        rightnode = rightepr.thisnode
        #左端节点是否是端节点
        if leftnode.name != request[0] and leftnode.name != request[1]:
            info_list = leftnode.req_mem[request]
            if len(info_list) > 1:
                #找到另一块存储
                if leftepr.thismemname != info_list[0][0]:
                    m2_name = info_list[0][0]
                else:
                    m2_name = info_list[1][0]
                m2 = leftnode.get_memory(m2_name)
                m1_name = leftepr.thismemname
                idx1 = leftepr.thisindex
                for idx2 in range(0,m2.capacity):
                    if m2._storage[idx2] != None and m2._storage[idx2].request == request:
                        self.swapping(leftnode,m1_name,m2_name,idx1,idx2,request)
                        return True 
        #左端节点是否是端节点
        if rightnode.name != request[0] and rightnode.name != request[1]:
            info_list = rightnode.req_mem[request]
            if len(info_list) > 1:
                #找到另一块存储
                if rightepr.thismemname != info_list[0][0]:
                    m2_name = info_list[0][0]           
                else:
                    m2_name = info_list[1][0]
                m2 = rightnode.get_memory(m2_name)
                m1_name = rightepr.thismemname
                idx1 = rightepr.thisindex
                for idx2 in range(0,m2.capacity):
                    if m2._storage[idx2] != None and m2._storage[idx2].request == request:
                        self.swapping(rightnode,m1_name,m2_name,idx1,idx2,request)
                        return True
