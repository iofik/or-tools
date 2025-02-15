#!/usr/bin/env python3
# Copyright 2010-2022 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Code sample to demonstrates how to rank intervals using a circuit."""

from typing import List, Sequence


from ortools.sat.python import cp_model


def rank_tasks_with_circuit(
    model: cp_model.CpModel,
    starts: Sequence[cp_model.IntVar],
    durations: Sequence[int],
    presences: Sequence[cp_model.IntVar],
    ranks: Sequence[cp_model.IntVar],
):
    """This method uses a circuit constraint to rank tasks.

    This method assumes that all starts are disjoint, meaning that all tasks have
    a strictly positive duration, and they appear in the same NoOverlap
    constraint.

    To implement this ranking, we will create a dense graph with num_tasks + 1
    nodes.
    The extra node (with id 0) will be used to decide which task is first with
    its only outgoing arc, and whhich task is last with its only incoming arc.
    Each task i will be associated with id i + 1, and an arc between i + 1 and j +
    1 indicates that j is the immediate successor of i.

    The circuit constraint ensures there is at most 1 hamiltonian path of
    length > 1. If no such path exists, then no tasks are active.

    The multiple enforced linear constraints are meant to ensure the compatibility
    between the order of starts and the order of ranks,

    Args:
      model: The CpModel to add the constraints to.
      starts: The array of starts variables of all tasks.
      durations: the durations of all tasks.
      presences: The array of presence variables of all tasks.
      ranks: The array of rank variables of all tasks.
    """

    num_tasks = len(starts)
    all_tasks = range(num_tasks)

    arcs: List[cp_model.ArcT] = []
    for i in all_tasks:
        # if node i is first.
        start_lit = model.NewBoolVar(f"start_{i}")
        arcs.append((0, i + 1, start_lit))
        model.Add(ranks[i] == 0).OnlyEnforceIf(start_lit)

        # As there are no other constraints on the problem, we can add this
        # redundant constraint.
        model.Add(starts[i] == 0).OnlyEnforceIf(start_lit)

        # if node i is last.
        end_lit = model.NewBoolVar(f"end_{i}")
        arcs.append((i + 1, 0, end_lit))

        for j in all_tasks:
            if i == j:
                arcs.append((i + 1, i + 1, presences[i].Not()))
                model.Add(ranks[i] == -1).OnlyEnforceIf(presences[i].Not())
            else:
                literal = model.NewBoolVar(f"arc_{i}_to_{j}")
                arcs.append((i + 1, j + 1, literal))
                model.Add(ranks[j] == ranks[i] + 1).OnlyEnforceIf(literal)

                # To perform the transitive reduction from precedences to successors,
                # we need to tie the starts of the tasks with 'literal'.
                # In a pure problem, the following inequality could be an equality.
                # It is not true in general.
                #
                # Note that we could use this literal to penalize the transition, add an
                # extra delay to the precedence.
                model.Add(starts[j] >= starts[i] + durations[i]).OnlyEnforceIf(literal)

    # Manage the empty circuit
    empty = model.NewBoolVar("empty")
    arcs.append((0, 0, empty))

    for i in all_tasks:
        model.AddImplication(empty, presences[i].Not())

    # Add the circuit constraint.
    model.AddCircuit(arcs)


def ranking_sample_sat():
    """Ranks tasks in a NoOverlap constraint."""

    model = cp_model.CpModel()
    horizon = 100
    num_tasks = 4
    all_tasks = range(num_tasks)

    starts = []
    durations = []
    intervals = []
    presences = []
    ranks = []

    # Creates intervals, half of them are optional.
    for t in all_tasks:
        start = model.NewIntVar(0, horizon, f"start[{t}]")
        duration = t + 1
        presence = model.NewBoolVar(f"presence[{t}]")
        interval = model.NewOptionalFixedSizeIntervalVar(
            start, duration, presence, f"opt_interval[{t}]"
        )
        if t < num_tasks // 2:
            model.Add(presence == 1)

        starts.append(start)
        durations.append(duration)
        intervals.append(interval)
        presences.append(presence)

        # Ranks = -1 if and only if the tasks is not performed.
        ranks.append(model.NewIntVar(-1, num_tasks - 1, f"rank[{t}]"))

    # Adds NoOverlap constraint.
    model.AddNoOverlap(intervals)

    # Adds ranking constraint.
    rank_tasks_with_circuit(model, starts, durations, presences, ranks)

    # Adds a constraint on ranks.
    model.Add(ranks[0] < ranks[1])

    # Creates makespan variable.
    makespan = model.NewIntVar(0, horizon, "makespan")
    for t in all_tasks:
        model.Add(starts[t] + durations[t] <= makespan).OnlyEnforceIf(presences[t])

    # Minimizes makespan - fixed gain per tasks performed.
    # As the fixed cost is less that the duration of the last interval,
    # the solver will not perform the last interval.
    model.Minimize(2 * makespan - 7 * sum(presences[t] for t in all_tasks))

    # Solves the model model.
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL:
        # Prints out the makespan and the start times and ranks of all tasks.
        print(f"Optimal cost: {solver.ObjectiveValue()}")
        print(f"Makespan: {solver.Value(makespan)}")
        for t in all_tasks:
            if solver.Value(presences[t]):
                print(
                    f"Task {t} starts at {solver.Value(starts[t])} "
                    f"with rank {solver.Value(ranks[t])}"
                )
            else:
                print(
                    f"Task {t} in not performed "
                    f"and ranked at {solver.Value(ranks[t])}"
                )
    else:
        print(f"Solver exited with nonoptimal status: {status}")


ranking_sample_sat()
