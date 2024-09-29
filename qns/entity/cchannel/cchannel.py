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

import json
from typing import Any, List, Optional, Union
from qns.models.delay.constdelay import ConstantDelayModel
from qns.models.delay.delay import DelayModel

from qns.simulator.simulator import Simulator
from qns.simulator.ts import Time
from qns.simulator.event import Event
import qns.utils.log as log
from qns.entity.entity import Entity
from qns.entity.node.node import QNode
from qns.utils.rnd import get_rand


class ClassicPacket(object):
    """
    ClassicPacket is the message that transfer on a ClassicChannel
    """

    def __init__(self, msg: Union[str, bytes, Any], src: QNode = None, dest: QNode = None):
        """
        Args:
            msg (Union[str, bytes, Any]): the message content.
                It can be a `str` or `bytes` type or can be dumpped to json.
            src (QNode): the source of this message
            dest (QNode): the destination of this message
        """
        self.is_json = False
        if not isinstance(msg, (str, bytes)):
            self.msg = json.dumps(msg)
            self.is_json = True
        else:
            self.msg = msg
        self.src = src
        self.dest = dest

    def encode(self) -> bytes:
        """
        encode the self.msg if it is a `str`

        Return:
            (bytes) a `bytes` object
        """
        if isinstance(self.msg, str):
            return self.msg.encode(encoding="utf-8")
        return self.msg

    def get(self):
        """
        get the message from packet

        Return:
            (Union[str, bytes, Any])
        """
        if self.is_json:
            return json.loads(self.msg)
        return self.msg

    def __len__(self) -> int:
        return len(self.msg)


class ClassicChannel(Entity):
    """
    ClassicChannel is the channel for classic message
    """
    def __init__(self, name: str = None, node_list: List[QNode] = [],
                 bandwidth: int = 0, delay: Union[float, DelayModel] = 0, length: Optional[float] = 0, drop_rate: float = 0,
                 max_buffer_size: int = 0):
        """
        Args:
            name (str): the name of this channel
            node_list (List[QNode]): a list of QNodes that it connects to
            bandwidth (int): the byte per second on this channel. 0 represents unlimited
            delay (Union[float, DelayModel]): the time delay for transmitting a packet. It is a float number or a ``DelayModel``
            length (float): the length of this channel
            drop_rate (float): the drop rate
            max_buffer_size (int): the max buffer size.
                If it is full, the next coming packet will be dropped. 0 represents unlimited.
        """
        super().__init__(name=name)
        self.node_list = node_list.copy()
        self.bandwidth = bandwidth
        self.delay_model = delay if isinstance(delay, DelayModel) else ConstantDelayModel(delay=delay)
        self.drop_rate = drop_rate
        self.length = length
        self.max_buffer_size = max_buffer_size

    def install(self, simulator: Simulator) -> None:
        '''
        ``install`` is called before ``simulator`` runs to initialize or set initial events

        Args:
            simulator (qns.simulator.simulator.Simulator): the simulator
        '''
        if not self._is_installed:
            self._simulator = simulator
            self._next_send_time = self._simulator.ts
            self._is_installed = True

    def send(self, packet: ClassicPacket, next_hop: QNode):
        """
        Send a classic packet to the next_hop

        Args:
            packet (ClassicPacket): the packet
            next_hop (QNode): the next hop QNode
        Raises:
            qns.entity.cchannel.cchannel.NextHopNotConnectionException:
                the next_hop is not connected to this channel
        """
        if next_hop not in self.node_list:
            raise NextHopNotConnectionException
        if self.bandwidth != 0:
            if self._next_send_time <= self._simulator.current_time:
                send_time = self._simulator.current_time
            else:
                send_time = self._next_send_time

            if self.max_buffer_size != 0 and send_time > self._simulator.current_time\
               + self._simulator.time(sec=self.max_buffer_size / self.bandwidth):
                # buffer is overflow
                log.debug(f"cchannel {self}: drop packet {packet} due to overflow")
                return

            self._next_send_time = send_time + \
                self._simulator.time(sec=len(packet) / self.bandwidth)
        else:
            send_time = self._simulator.current_time

        # random drop
        if get_rand() < self.drop_rate:
            log.debug(f"cchannel {self}: drop packet {packet} due to drop rate")
            return
        #  add delay
        recv_time = send_time + self._simulator.time(sec=self.delay_model.calculate())

        send_event = RecvClassicPacket(recv_time, name=None, by=self,
                                       cchannel=self, packet=packet, dest=next_hop)
        self._simulator.add_event(send_event)

    def __repr__(self) -> str:
        if self.name is not None:
            return "<cchannel "+self.name+">"
        return super().__repr__()


class NextHopNotConnectionException(Exception):
    pass


class RecvClassicPacket(Event):
    """
    The event for a QNode to receive a classic packet
    """
    def __init__(self, t: Optional[Time] = None, name: Optional[str] = None,
                 cchannel: ClassicChannel = None, packet: ClassicPacket = None, dest: QNode = None,
                 by: Optional[Any] = None):
        super().__init__(t=t, name=name, by=by)
        self.cchannel = cchannel
        self.packet = packet
        self.dest = dest

    def invoke(self) -> None:
        self.dest.handle(self)
