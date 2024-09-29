#    SimQN: a discrete-event simulator for the quantum networks
#    Copyright (C) 2021-2022 Lutong Chen, Jian Li, Kaiping Xue
#    University of Science and Technology of China, USTC.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from qns.entity.node.app import Application
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.entity.node.node import QNode
from typing import Dict, List, Optional, Tuple
from qns.network.topology import Topology


class dumbbell(Topology):
    """
    LineTopology includes `nodes_number` Qnodes. The topology is a line pattern.
    """
    def __init__(self, nodes_number, nodes_apps: List[Application] = [],
                 qchannel_args: Dict = {}, cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {}):
        super().__init__(nodes_number, nodes_apps=nodes_apps,
                         qchannel_args=qchannel_args, cchannel_args=cchannel_args,
                         memory_args=memory_args)

    def build(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        nl: List[QNode] = []
        ll = []
        for i in range(self.nodes_number):
            n = QNode(f"n{i+1}")
            nl.append(n)
            
        link1 = QuantumChannel(name=f"l{1}", **self.qchannel_args)
        ll.append(link1)
        nl[0].add_qchannel(link1)
        nl[1].add_qchannel(link1)

        link2 = QuantumChannel(name=f"l{2}", **self.qchannel_args)
        ll.append(link2)
        nl[1].add_qchannel(link2)
        nl[2].add_qchannel(link2)

        link3 = QuantumChannel(name=f"l{3}", **self.qchannel_args)
        ll.append(link3)
        nl[2].add_qchannel(link3)
        nl[3].add_qchannel(link3)

        link4 = QuantumChannel(name=f"l{4}", **self.qchannel_args)
        ll.append(link4)
        nl[1].add_qchannel(link4)
        nl[4].add_qchannel(link4)

        link5 = QuantumChannel(name=f"l{5}", **self.qchannel_args)
        ll.append(link5)
        nl[2].add_qchannel(link5)
        nl[5].add_qchannel(link5)

        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll
