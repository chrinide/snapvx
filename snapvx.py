## snapvx

from snap import *
from cvxpy import *
import numpy

class TUNGraphVX(TUNGraph):

    # node_objectives  = {int NId : CVXPY Expression}
    # node_variables   = {int NId : CVXPY Variable}
    # node_constraints = {int NId : [CVXPY Constraint]}
    # edge_objectives  = {(int NId1, int NId2) : CVXPY Expression}
    # edge_constraints = {(int NId1, int NId2) : [CVXPY Constraint]}
    # (ADMM) node_values = {int NId : numpy array}
    def __init__(self, Nodes=0, Edges=0):
        self.node_objectives = {}
        self.node_variables = {}
        self.node_constraints = {}
        self.edge_objectives = {}
        self.edge_constraints = {}
        self.node_values = {}
        TUNGraph.__init__(self, Nodes, Edges)

    # Iterates through all nodes and edges. Currently adds objectives together.
    # Option of specifying Maximize() or the default Minimize().
    # Option to use ADMM.
    # Graph status and value properties will be set.
    def Solve(self, M=Minimize, useADMM=False):
        if useADMM:
            self.__SolveADMM()
            return
        objective = 0
        constraints = []
        ni = TUNGraph.BegNI(self)
        for i in xrange(TUNGraph.GetNodes(self)):
            nid = ni.GetId()
            objective += self.node_objectives[nid]
            constraints += self.node_constraints[nid]
            ni.Next()
        ei = TUNGraph.BegEI(self)
        for i in xrange(TUNGraph.GetEdges(self)):
            etup = self.__GetEdgeTup(ei.GetSrcNId(), ei.GetDstNId())
            objective += self.edge_objectives[etup]
            constraints += self.edge_constraints[etup]
            ei.Next()
        objective = M(objective)
        problem = Problem(objective, constraints)
        problem.solve()
        self.status = problem.status
        self.value = problem.value

    # First draft of ADMM algorithm. Currently done serially.
    # TODO: Use multiprocessing module to make distributed.
    # TODO: Improve data structure for storing u and z values.
    def __SolveADMM(self):
        print 'Solving with ADMM...'
        # Hash table storing the numpy array values of x, z, and u.
        admm_node_vals = {}
        admm_edge_vals = {}
        (Z_IJ, Z_JI, U_IJ, U_JI) = (0, 1, 2, 3)
        num_iterations = 50
        rho = 1.0

        # Initialize x variable for each node.
        ni = TUNGraph.BegNI(self)
        for i in xrange(TUNGraph.GetNodes(self)):
            nid = ni.GetId()
            varsize = self.node_variables[nid].size
            admm_node_vals[nid] = numpy.zeros((varsize[0], varsize[1]))
            ni.Next()
        # Initialize z and u variables for each edge.
        ei = TUNGraph.BegEI(self)
        for i in xrange(TUNGraph.GetEdges(self)):
            etup = self.__GetEdgeTup(ei.GetSrcNId(), ei.GetDstNId())
            varsize_i = self.node_variables[etup[0]].size
            z_ij = numpy.zeros((varsize_i[0], varsize_i[1]))
            u_ij = numpy.zeros((varsize_i[0], varsize_i[1]))
            varsize_j = self.node_variables[etup[1]].size
            z_ji = numpy.zeros((varsize_j[0], varsize_j[1]))
            u_ji = numpy.zeros((varsize_j[0], varsize_j[1]))
            admm_edge_vals[etup] = [z_ij, z_ji, u_ij, u_ji]
            ei.Next()

        # Run ADMM for a finite number of iterations.
        # TODO: Stopping conditions.
        for i in xrange(num_iterations):
            # Debugging information prints current iteration #.
            print '..%d' % i

            # x update: Update x_i with z and u variables constant.
            ni = TUNGraph.BegNI(self)
            for i in xrange(TUNGraph.GetNodes(self)):
                nid = ni.GetId()
                var = self.node_variables[nid]
                norms = 0
                # Sum over all neighbors.
                for j in xrange(ni.GetDeg()):
                    nbrid = ni.GetNbrNId(j)
                    (zi, ui) = (Z_IJ, U_IJ) if (nid < nbrid) else (Z_JI, U_JI)
                    edge_vals = admm_edge_vals[self.__GetEdgeTup(nid, nbrid)]
                    norms += square(norm(var - edge_vals[zi] + edge_vals[ui]))
                objective = self.node_objectives[nid] + (rho / 2) * norms
                objective = Minimize(objective)
                problem = Problem(objective, [])
                problem.solve()
                admm_node_vals[nid] = var.value
                ni.Next()

            # z update: Update z_ij and z_ji with x and u variables constant.
            ei = TUNGraph.BegEI(self)
            for i in xrange(TUNGraph.GetEdges(self)):
                etup = self.__GetEdgeTup(ei.GetSrcNId(), ei.GetDstNId())
                edge_vals = admm_edge_vals[etup]
                node_val_i = admm_node_vals[etup[0]]
                node_val_j = admm_node_vals[etup[1]]
                node_var_i = self.node_variables[etup[0]]
                node_var_j = self.node_variables[etup[1]]
                objective = self.edge_objectives[etup]
                o = node_val_i - node_var_i + edge_vals[U_IJ]
                objective += (rho / 2) * square(norm(o))
                o = node_val_j - node_var_j + edge_vals[U_JI]
                objective += (rho / 2) * square(norm(o))
                objective = Minimize(objective)
                problem = Problem(objective, [])
                problem.solve()
                # TODO: What if both node variables are not in the edge obj?
                edge_vals[Z_IJ] = node_var_i.value
                edge_vals[Z_JI] = node_var_j.value
                ei.Next()

            # u update: Update u with x and z variables constant.
            ei = TUNGraph.BegEI(self)
            for i in xrange(TUNGraph.GetEdges(self)):
                etup = self.__GetEdgeTup(ei.GetSrcNId(), ei.GetDstNId())
                edge_vals = admm_edge_vals[etup]
                edge_vals[U_IJ] += admm_node_vals[etup[0]] - edge_vals[Z_IJ]
                edge_vals[U_JI] += admm_node_vals[etup[1]] - edge_vals[Z_JI]
                ei.Next()

        self.node_values = admm_node_vals
        self.status = 'TODO'
        self.value = 'TODO'

    # API to get node variable value after solving with ADMM.
    def GetNodeValue(self, NId):
        self.__VerifyNId(NId)
        return self.node_values[NId] if (NId in self.node_values) else None


    # Helper method to verify existence of an NId.
    def __VerifyNId(self, NId):
        if not TUNGraph.IsNode(self, NId):
            raise Exception('Node %d does not exist.' % NId)

    # Adds a Node to the TUNGraph and stores the corresponding CVX information.
    def AddNode(self, NId, Objective, Variable, Constraints=[]):
        self.node_objectives[NId] = Objective
        self.node_variables[NId] = Variable
        self.node_constraints[NId] = Constraints
        return TUNGraph.AddNode(self, NId)

    def SetNodeObjective(self, NId, Objective):
        self.__VerifyNId(NId)
        self.node_objectives[NId] = Objective

    def GetNodeObjective(self, NId):
        self.__VerifyNId(NId)
        return self.node_objectives[NId]

    def SetNodeVariable(self, NId, Variable):
        self.__VerifyNId(NId)
        self.node_variables[NId] = Variable

    def GetNodeVariable(self, NId):
        self.__VerifyNId(NId)
        return self.node_variables[NId]

    def SetNodeConstraints(self, NId, Constraints):
        self.__VerifyNId(NId)
        self.node_constraints[NId] = Constraints

    def GetNodeConstraints(self, NId):
        self.__VerifyNId(NId)
        return self.node_constraints[NId]

    # Helper method to get a tuple representing an edge. The smaller NId
    # goes first.
    def __GetEdgeTup(self, NId1, NId2):
        return (NId1, NId2) if NId1 < NId2 else (NId2, NId1)

    # Helper method to verify existence of an edge.
    def __VerifyEdgeTup(self, ETup):
        if not TUNGraph.IsEdge(self, ETup[0], ETup[1]):
            raise Exception('Edge {%d,%d} does not exist.' % ETup)

    # Adds an Edge to the TUNGraph and stores the corresponding CVX information.
    def AddEdge(self, SrcNId, DstNId, Objective, Constraints=[]):
        ETup = self.__GetEdgeTup(SrcNId, DstNId)
        self.edge_objectives[ETup] = Objective
        self.edge_constraints[ETup] = Constraints
        return TUNGraph.AddEdge(self, SrcNId, DstNId)

    def SetEdgeObjective(self, SrcNId, DstNId, Objective):
        ETup = self.__GetEdgeTup(SrcNId, DstNId)
        self.__VerifyEdgeTup(ETup)
        self.edge_objectives[ETup] = Objective

    def GetEdgeObjective(self, SrcNId, DstNId):
        ETup = self.__GetEdgeTup(SrcNId, DstNId)
        self.__VerifyEdgeTup(ETup)
        return self.edge_objectives[ETup]

    def SetEdgeConstraints(self, SrcNId, DstNId, Constraints):
        ETup = self.__GetEdgeTup(SrcNId, DstNId)
        self.__VerifyEdgeTup(ETup)
        self.edge_constraints[ETup] = Constraints

    def GetEdgeConstraints(self, SrcNId, DstNId):
        ETup = self.__GetEdgeTup(SrcNId, DstNId)
        self.__VerifyEdgeTup(ETup)
        return self.edge_constraints[ETup]