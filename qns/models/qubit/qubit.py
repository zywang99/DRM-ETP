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

from typing import Any, List, Optional
import numpy as np

from qns.models.qubit.const import QUBIT_STATE_0, QUBIT_STATE_1,\
        QUBIT_STATE_P, QUBIT_STATE_N, QUBIT_STATE_L, QUBIT_STATE_R
from qns.models.qubit.utils import single_gate_expand, partial_trace, kron
from qns.models.core.backend import QuantumModel
from qns.models.qubit.errors import QStateBaseError, QStateQubitNotInStateError,\
                                    QStateSizeNotMatchError, OperatorNotMatchError
from qns.utils.rnd import get_rand


class QState(object):
    """
    QState is the state of one (or multiple) qubits
    """
    def __init__(self, qubits: List["Qubit"] = [], state: Optional[np.ndarray] = QUBIT_STATE_0,
                 rho: Optional[np.ndarray] = None, name: Optional[str] = None):
        """
        Args:
            qubits (List[Qubit]): a list of qubits in this quantum state
            state: the state vector of this state, either ``state`` or ``rho`` can be used to present a state
            rho: the density matrix of this state, either ``state`` or ``rho`` can be used to present a state
            name (str): the name of this state
        """
        self.num = len(qubits)
        self.name = name
        self.qubits = qubits
        self.rho = None

        if rho is None:
            if len(state) != 2**self.num:
                raise QStateSizeNotMatchError
            self.rho = np.dot(state, state.T.conjugate())
        else:
            if self.num != np.log2(rho.shape[0]) or self.num != np.log2(rho.shape[1]):
                raise QStateSizeNotMatchError
            if abs(1 - rho.trace()) > 0.0000000001:
                # trace = 1
                raise QStateSizeNotMatchError
            self.rho = rho

    def measure(self, qubit: "Qubit" = None, base: str = "Z") -> int:
        """
        Measure this qubit using Z basis
        Args:
            qubit (Qubit): the measuring qubit
            base: the measure base, "Z", "X" or "Y"

        Returns:
            0: QUBIT_STATE_0 state
            1: QUBIT_STATE_1 state
        """
        M_0 = None
        M_1 = None
        S_0 = None
        S_1 = None
        if base == "Z":
            M_0 = np.array([[1, 0], [0, 0]])
            M_1 = np.array([[0, 0], [0, 1]])
            S_0 = QUBIT_STATE_0
            S_1 = QUBIT_STATE_1
        elif base == "X":
            M_0 = 1/2 * np.array([[1, 1], [1, 1]])
            M_1 = 1/2 * np.array([[1, -1], [-1, 1]])
            S_0 = QUBIT_STATE_P
            S_1 = QUBIT_STATE_N
        elif base == "Y":
            M_0 = 1/2 * np.array([[1, -1j], [1j, 1]])
            M_1 = 1/2 * np.array([[1, 1j], [-1j, 1]])
            S_0 = QUBIT_STATE_R
            S_1 = QUBIT_STATE_L
        else:
            raise QStateBaseError

        try:
            idx = self.qubits.index(qubit)
            shift = self.num - idx - 1
            assert (shift >= 0)
        except AssertionError:
            raise QStateQubitNotInStateError

        Full_M_0 = np.array([[1]])
        Full_M_1 = np.array([[1]])
        for i in range(self.num):
            if i == idx:
                Full_M_0 = kron(Full_M_0, M_0)
                Full_M_1 = kron(Full_M_1, M_1)
            else:
                Full_M_0 = kron(Full_M_0, np.array([[1, 0], [0, 1]]))
                Full_M_1 = kron(Full_M_1, np.array([[1, 0], [0, 1]]))

        poss_0 = np.trace(np.dot(Full_M_0.T.conjugate(), np.dot(Full_M_0, self.rho)))
        rn = get_rand()

        if rn < poss_0:
            ret = 0
            ret_s = S_0
            self.rho = np.dot(Full_M_0, np.dot(self.rho, Full_M_0.T.conjugate())) / poss_0
        else:
            ret = 1
            ret_s = S_1
            self.rho = np.dot(Full_M_1, np.dot(self.rho, Full_M_1.T.conjugate())) / (1-poss_0)

        self.rho = partial_trace(self.rho, idx)
        self.num -= 1
        self.qubits.remove(qubit)

        ns = QState([qubit], state=ret_s)
        qubit.state = ns
        return ret

    def operate(self, operator: np.ndarray):
        """
        transform using `operator`

        Args:
            operator (np.ndarray): the operator
        Raises:
            OperatorNotMatchError
        """
        operator_size = operator.shape
        if operator_size == (2**self.num, 2**self.num):
            # joint qubit operate
            full_operator = operator
        else:
            raise OperatorNotMatchError
        self.rho = np.dot(full_operator, np.dot(self.rho, full_operator.T.conjugate()))

    def stochastic_operate(self, list_operators: List[np.ndarray] = [], list_p: List[float] = []):
        """
        A stochastic operate progess. It usually turns a pure state into a mixed state.

        Args:
            list_operators (List[np.ndarray]): a list of operators
            list_p (List[float]): a list of possibility
        Raises:
            OperatorNotMatchError
        """
        new_state = np.zeros((2**self.num, 2**self.num), dtype=complex)

        if len(list_operators) != len(list_p):
            raise OperatorNotMatchError("Not match number between operators and possibilities")

        sum = 0.0
        for p in list_p:
            if p < 0 or p > 1:
                raise OperatorNotMatchError("possibility not in range")
            sum += p

        if abs(1-sum) >= 1e-6:
            raise OperatorNotMatchError("Probabilities are not normalized")

        for idx, operator in enumerate(list_operators):
            operator_size = operator.shape
            if operator_size == (2**self.num, 2**self.num):
                full_operator = operator
            else:
                raise OperatorNotMatchError
            new_state += list_p[idx] * np.dot(full_operator, np.dot(self.rho, full_operator.T.conjugate()))
        self.rho = new_state

    def equal(self, other_state: "QState") -> bool:
        """
        compare two state vectors, return True if they are the same

        Args:
            other_state (QState): the second QState
        """
        return np.all(self.rho == other_state.rho)

    def is_pure_state(self, eps: float = 0.000_001) -> bool:
        """
        Args:
            eps: the accuracy

        Returns:
            bool, if the state is a pure state
        """
        return abs(np.trace(np.dot(self.rho, self.rho)) - 1) <= eps

    def state(self) -> np.ndarray:
        """
        If the state is a pure state, return the state vector, or return None

        Returns:
            The pure state vector
        """
        if not self.is_pure_state():
            print(self.rho.T.conjugate() * self.rho)
            return None
        evs = np.linalg.eig(self.rho)
        max_idx = 0
        for idx, i in enumerate(evs[0]):
            if i > evs[0][max_idx]:
                max_idx = idx
        return evs[1][:, max_idx].reshape((2**self.num, 1))

    def __repr__(self) -> str:
        if self.name is not None:
            return "<qubit state "+self.name+">"
        return str(self.rho)


class Qubit(QuantumModel):
    """
    Represent a qubit
    """

    def __init__(self, state=QUBIT_STATE_0, rho: np.ndarray = None,
                 operate_decoherence_rate: float = 0, measure_decoherence_rate: float = 0,
                 name: Optional[str] = None):
        """
        Args:
            state (list): the initial state of a qubit, default is |0> = [1, 0]^T
            operate_decoherence_rate (float): the operate decoherence rate
            measure_decoherence_rate (float): the measure decoherence rate
            name (str): the qubit's name
        """

        self.name = name
        self.state = QState([self], state=state, rho=rho)
        self.operate_decoherence_rate = operate_decoherence_rate
        self.measure_decoherence_rate = measure_decoherence_rate

    def measure(self):
        """
        Measure this qubit using Z basis

        Returns:
            0: QUBIT_STATE_0 state
            1: QUBIT_STATE_1 state
        """
        self.measure_error_model(decoherence_rate=self.measure_decoherence_rate)
        return self.state.measure(self)

    def measureX(self):
        """
        Measure this qubit using X basis.

        Returns:
            0: QUBIT_STATE_P state
            1: QUBIT_STATE_N state
        """
        self.measure_error_model(self.measure_decoherence_rate)
        return self.state.measure(self, "X")

    def measureY(self):
        """
        Measure this qubit using Y basis.
        Only for not entangled qubits.

        Returns:
            0: QUBIT_STATE_R state
            1: QUBIT_STATE_L state
        """
        self.measure_error_model(self.measure_decoherence_rate)
        return self.state.measure(self, "Y")

    def measureZ(self):
        """
        Measure this qubit using Z basis

        Returns:
            0: QUBIT_STATE_0 state
            1: QUBIT_STATE_1 state
        """
        self.measure_error_model(self.measure_decoherence_rate)
        return self.measure()

    def operate(self, operator: Any) -> None:
        """
        Perfrom a operate on this qubit

        Args:
            operator (Union[SingleQubitGate, np.ndarray]): an operator matrix, or a quantum gate in qubit.gate
        """
        self.operate_error_model(self.operate_decoherence_rate)
        from qns.models.qubit.gate import SingleQubitGate
        if isinstance(operator, SingleQubitGate):
            operator(self)
            return
        full_operator = single_gate_expand(self, operator)
        self.state.operate(full_operator)

    def _operate_without_error(self, operator: Any) -> None:
        """
        Perfrom a operate on this qubit

        Args:
            operator (Union[SingleQubitGate, np.ndarray]): an operator matrix, or a quantum gate in qubit.gate
        """
        from qns.models.qubit.gate import SingleQubitGate
        if isinstance(operator, SingleQubitGate):
            operator(self)
            return
        full_operator = single_gate_expand(self, operator)
        self.state.operate(full_operator)

    def stochastic_operate(self, list_operators: List[np.ndarray] = [], list_p: List[float] = []):
        """
        A stochastic operate on this qubit. It usually turns a pure state into a mixed state.

        Args:
            list_operators (List[np.ndarray]): a list of operators
            list_p (List[float]): a list of possibility
        Raises:
            OperatorNotMatchError
        """
        from qns.models.qubit.gate import SingleQubitGate
        full_operators_list = []
        for operator in list_operators:
            if isinstance(operator, SingleQubitGate):
                full_operators_list.append(single_gate_expand(self, operator._operator))
            else:
                full_operators_list.append(single_gate_expand(self, operator))
        self.state.stochastic_operate(full_operators_list, list_p)

    def __repr__(self) -> str:
        if self.name is not None:
            return "<qubit "+self.name+">"
        return super().__repr__()

    def store_error_model(self, t: Optional[float] = 0, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The default error model for storing a qubit in quantum memory.
        The default behavior is doing nothing

        Args:
            t: the time stored in a quantum memory. The unit it second.
            decoherence_rate (float): the decoherence rate in Db.
            kwargs: other parameters
        """
        pass

    def transfer_error_model(self, length: Optional[float] = 0, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The default error model for transmitting this qubit
        The default behavior is doing nothing

        Args:
            length (float): the length of the channel
            decoherence_rate (float): the decoherence rate
            kwargs: other parameters
        """
        pass

    def operate_error_model(self, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The error model for operating a qubit.
        This function will change the quantum state.

        Args:
            decoherence_rate (float): the decoherency rate
            kwargs: other parameters
        """
        pass

    def measure_error_model(self, decoherence_rate: Optional[float] = 0, **kwargs):
        """
        The error model for measuring a qubit.
        This function will change the quantum state.

        Args:
            decoherence_rate (float): the decoherency rate
            kwargs: other parameters
        """
        pass
