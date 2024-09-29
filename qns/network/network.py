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

from typing import Dict, List, Optional, Tuple
from qns.entity import QNode, QuantumChannel, QuantumMemory, ClassicChannel
from qns.network.topology import Topology
from qns.network.route import RouteImpl, DijkstraRouteAlgorithm
from qns.network.requests import Request
from qns.network.topology.topo import ClassicTopology
from qns.simulator.simulator import Simulator
from qns.utils.rnd import get_randint


class QuantumNetwork(object):
    """
    QuantumNetwork includes several quantum nodes, channels and a special topology
    """

    def __init__(self, topo: Optional[Topology] = None, route: Optional[RouteImpl] = None,
                 classic_topo: Optional[ClassicTopology] = ClassicTopology.Empty,
                 name: Optional[str] = None):
        """
        Args:
            topo: a `Topology` class. If topo is not None, a special quantum topology is built.
            route: the route implement. If route is None, the dijkstra algorithm will be used
            classic_topo (ClassicTopo): a `ClassicTopo` enum class.
        """
        self.name = name
        self.cchannels: List[ClassicChannel] = []
        if topo is None:
            self.nodes: List[QNode] = []
            self.qchannels: List[QuantumChannel] = []
        else:
            self.nodes, self.qchannels = topo.build()
            if classic_topo is not None:
                self.cchannels = topo.add_cchannels(classic_topo=classic_topo,
                                                    nl=self.nodes, ll=self.qchannels)
            for n in self.nodes:
                n.add_network(self)

        if route is None:
            self.route: RouteImpl = DijkstraRouteAlgorithm()
        else:
            self.route: RouteImpl = route
        self.requests: List[Request] = []

    def install(self, s: Simulator):
        '''
        install all nodes (including channels, memories and applications) in this network

        Args:
            simulator (qns.simulator.simulator.Simulator): the simulator
        '''
        for n in self.nodes:
            n.install(s)

    def add_node(self, node: QNode):
        """
        add a QNode into this network.

        Args:
            node (qns.entity.node.node.QNode): the inserting node
        """
        self.nodes.append(node)
        node.add_network(self)

    def get_node(self, name: str):
        """
        get the QNode by its name

        Args:
            name (str): its name
        Returns:
            the QNode
        """
        for n in self.nodes:
            if n.name == name:
                return n
        return None

    def add_qchannel(self, qchannel: QuantumChannel):
        """
        add a QuantumChannel into this network.

        Args:
            qchannel (qns.entity.qchannel.qchannel.QuantumChannel): the inserting QuantumChannel
        """
        self.qchannels.append(qchannel)

    def get_qchannel(self, name: str):
        """
        get the QuantumChannel by its name

        Args:
            name (str): its name
        Returns:
            the QuantumChannel
        """
        for n in self.qchannels:
            if n.name == name:
                return n
        return None

    def add_cchannel(self, cchannel: ClassicChannel):
        """
        add a ClassicChannel into this network.

        Args:
            cchannel (qns.entity.cchannel.cchannel.ClassicChannel): the inserting ClassicChannel
        """
        self.cchannels.append(cchannel)

    def get_cchannel(self, name: str):
        """
        get the ClassicChannel by its name

        Args:
            name (str): its name
        Returns:
            the ClassicChannel
        """
        for n in self.cchannels:
            if n.name == name:
                return n
        return None

    def add_memories(self, capacity: int = 0, decoherence_rate: Optional[float] = 0, store_error_model_args: dict = {}):
        """
        Add quantum memories to every nodes in this network

        Args:
            capacity (int): the capacity of the quantum memory
            decoherence_rate (float): the decoherence rate
            store_error_model_args: the arguments for store_error_model
        """
        for idx, n in enumerate(self.nodes):
            m = QuantumMemory(name=f"m{idx}", node=n, capacity=capacity, decoherence_rate=decoherence_rate,
                              store_error_model_args=store_error_model_args)
            n.add_memory(m)

    def build_route(self):
        """
        build static route tables for each nodes
        """
        self.route.build(self.nodes, self.qchannels)

    def query_route(self, src: QNode, dest: QNode) -> List[Tuple[float, QNode, List[QNode]]]:
        """
        query the metric, nexthop and the path

        Args:
            src: the source node
            dest: the destination node

        Returns:
            A list of route paths. The result should be sortted by the priority.
            The element is a tuple containing: metric, the next-hop and the whole path.
        """
        return self.route.query(src, dest)

    def add_request(self, src: QNode, dest: QNode, attr: Dict = {}):
        """
        Add a request (SD-pair) to the network

        Args:
            src: the source node
            dest: the destination node
            attr: other attributions
        """
        req = Request(src=src, dest=dest, attr=attr)
        self.requests.append(req)
        src.add_request(req)
        dest.add_request(req)

    def random_requests(self, number: int, allow_overlay: bool = False, attr: Dict = {}):
        """
        Generate random requests

        Args:
            number (int): the number of requests
            allow_overlay (bool): allow a node to be the source or destination in multiple requests
            attr (Dict): request attributions
        """
        used_nodes: List[int] = []
        nnodes = len(self.nodes)

        if number < 1:
            raise QNSNetworkError("number of requests should be large than 1")

        if not allow_overlay and number * 2 > nnodes:
            raise QNSNetworkError("Too many requests")

        for n in self.nodes:
            n.clear_request()
        self.requests.clear()

        for _ in range(number):
            while True:
                src_idx = get_randint(0, nnodes - 1)
                dest_idx = get_randint(0, nnodes - 1)
                if src_idx == dest_idx:
                    continue
                if not allow_overlay and src_idx in used_nodes:
                    continue
                if not allow_overlay and dest_idx in used_nodes:
                    continue
                if not allow_overlay:
                    used_nodes.append(src_idx)
                    used_nodes.append(dest_idx)
                break

            src = self.nodes[src_idx]
            dest = self.nodes[dest_idx]
            req = Request(src=src, dest=dest, attr=attr)
            self.requests.append(req)
            src.add_request(req)
            dest.add_request(req)


class QNSNetworkError(Exception):
    pass
