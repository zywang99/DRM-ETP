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

from typing import Optional, List
from qns.models.epr.entanglement import BaseEntanglement
from qns.models.core.backend import QuantumModel
from qns.models.qubit.qubit import Qubit, QState
from qns.models.qubit.const import QUBIT_STATE_0, QUBIT_STATE_P
import numpy as np

from qns.utils.rnd import get_rand


class WernerStateEntanglement(BaseEntanglement, QuantumModel):
    """
    `WernerStateEntanglement` is a pair of entangled qubits in Werner State with a hidden-variable.
    """
    def __init__(self, fidelity: float = 1, name: Optional[str] = None):
        """
        generate an entanglement with certain fidelity

        Args:
            fidelity (float): the fidelity
            name (str): the entanglement name
        """
        self.w = (fidelity * 4 - 1) / 3
        self.name = name
        self.is_decoherenced = False

    @property
    def fidelity(self) -> float:
        return (self.w * 3 + 1) / 4

    @fidelity.setter
    def fidelity(self, fidelity: float = 1):
        self.w = (fidelity * 4 - 1) / 3

    def swapping(self, epr: "WernerStateEntanglement", name: Optional[str] = None):
        """
        Use `self` and `epr` to perfrom swapping and distribute a new entanglement

        Args:
            epr (WernerEntanglement): another entanglement
            name (str): the name of the new entanglement
        Returns:
            the new distributed entanglement
        """
        ne = WernerStateEntanglement(name=name)
        if self.is_decoherenced or epr.is_decoherenced:
            ne.is_decoherenced = True
            ne.fidelity = 0
        epr.is_decoherenced = True
        self.is_decoherenced = True
        ne.w = self.w * epr.w
        return ne

    def distillation(self, epr: "WernerStateEntanglement", name: Optional[str] = None):
        """
        Use `self` and `epr` to perfrom distillation and distribute a new entanglement.
        Using Bennett 96 protocol and estimate lower bound.

        Args:
            epr (WernerEntanglement): another entanglement
            name (str): the name of the new entanglement
        Returns:
            the new distributed entanglement
        """
        ne = WernerStateEntanglement()
        if self.is_decoherenced or epr.is_decoherenced:
            ne.is_decoherenced = True
            ne.fidelity = 0
            return
        epr.is_decoherenced = True
        self.is_decoherenced = True
        fmin = min(self.fidelity, epr.fidelity)

        if get_rand() > (fmin ** 2 + 5 / 9 * (1 - fmin) ** 2 + 2 / 3 * fmin * (1 - fmin)):
            ne.is_decoherenced = True
            ne.fidelity = 0
            return
        ne.fidelity = (fmin ** 2 + (1 - fmin) ** 2 / 9) /\
                      (fmin ** 2 + 5 / 9 * (1 - fmin) ** 2 + 2 / 3 * fmin * (1 - fmin))
        return ne

    def store_error_model(self, t: float, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The default error model for storing this entangled pair in a quantum memory.
        The default behavior is: w = w*e^{-decoherence_rate*t}, default a = 0

        Args:
            t: the time stored in a quantum memory. The unit it second.
            decoherence_rate: the decoherence rate, equals to 1/T_coh, where T_coh is the coherence time.
            kwargs: other parameters
        """
        self.w = self.w * np.exp(-decoherence_rate * t)

    def transfer_error_model(self, length: float, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The default error model for transmitting this entanglement.
        The success possibility of transmitting is: w = w* e^{decoherence_rate * length}

        Args:
            length (float): the length of the channel
            kwargs: other parameters
        """
        self.w = self.w * np.exp(-decoherence_rate * length)

    def to_qubits(self) -> List[Qubit]:
        if self.is_decoherenced:
            q0 = Qubit(state=QUBIT_STATE_P, name="q0")
            q1 = Qubit(state=QUBIT_STATE_P, name="q1")
            return [q0, q1]

        q0 = Qubit(state=QUBIT_STATE_0, name="q0")
        q1 = Qubit(state=QUBIT_STATE_0, name="q1")

        phi_p = 1/np.sqrt(2) * np.array([[1], [0], [0], [1]])
        rho = self.w * np.dot(phi_p, phi_p.T.conjugate()) + (1-self.w)/4 * np.identity(4)
        print(rho)
        qs = QState([q0, q1], rho=rho)
        q0.state = qs
        q1.state = qs
        self.is_decoherenced = True
        return [q0, q1]
