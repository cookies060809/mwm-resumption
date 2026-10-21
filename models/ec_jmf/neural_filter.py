"""Differentiable finite EC-JMF topology; probabilities are rebuilt by PyTorch.

Only states/edges and references to named gates are cached. No labels or learned
predictions enter compilation. The float reference filter remains unchanged.
"""
from dataclasses import replace

import torch

from models.ec_jmf.structured import StructuredModel, GoalState, JointState, Mechanisms
from models.ecr_mwm.neural_data import state_features, MENTAL_DIM

GATES = ('access_uncertain', 'understanding_uncertain', 'accept_message',
         'invalid_abandon', 'action_validity', 'world_uncertain', 'recall_next',
         'initial_ready', 'initial_blocked')
LABELS = {'V':('VALID','CANCELLED','FULFILLED','UNKNOWN'),
          'F':('READY','BLOCKED','UNKNOWN'), 'A':('ACCESSED','NOT_ACCESSED','UNCERTAIN'),
          'B':('BELIEVES_VALID','BELIEVES_INVALID','UNRESOLVED','UNKNOWN'),
          'C':('ACTIVE','SUSPENDED','ABANDONED','COMPLETED','UNKNOWN'),
          'Q':tuple(f'k{i}' for i in range(8))+('UNKNOWN','NOT_APPLICABLE')}
OFFSETS = {}; _size = 0
for _factor, _labels in LABELS.items():
    OFFSETS[_factor] = (_size, _size+len(_labels)); _size += len(_labels)
FACTOR_DIM = _size


class Probability:
    """A nonnegative monomial in p_gate or (1-p_gate), not a handwritten gradient."""
    def __init__(self, coefficient=1.0, factors=()):
        self.coefficient, self.factors = coefficient, factors

    def __mul__(self, other):
        if not isinstance(other, Probability):
            other = Probability(other)
        return Probability(self.coefficient*other.coefficient, self.factors+other.factors)

    __rmul__ = __mul__

    def __truediv__(self, value):
        return Probability(self.coefficient/value, self.factors)

    def __rsub__(self, value):
        if value != 1 or self.coefficient != 1 or len(self.factors) != 1:
            raise ValueError('NOT_A_PRIMITIVE_GATE')
        context, gate, positive = self.factors[0]
        return Probability(1.0, ((context, gate, not positive),))

    def __bool__(self):
        return self.coefficient != 0


def q_label(goal, graphs):
    return f'k{graphs[goal.goal_id]["steps"].index(goal.q)}' if goal.q in graphs[goal.goal_id]['steps'] else goal.q


def factor_vector(state, target, graphs):
    goal = state.goal(target)
    values = []
    for factor,labels in LABELS.items():
        label = q_label(goal,graphs) if factor == 'Q' else goal.factor(factor)
        values.extend(float(label == x) for x in labels)
    return values


class TopologyModel(StructuredModel):
    def __init__(self, adapted, variant):
        mechanisms = Mechanisms(access_gate=variant!='A1', comprehension_gate=variant!='A1',
                                learned_gates=variant!='A6')
        super().__init__(adapted, mechanisms=mechanisms)
        self.variant = variant
        self.contexts, self.context_keys = [], {}
        self.stage, self.previous = 0, None
        self.window_start = max(0,len(adapted['events'])-5) if variant == 'A3' else 0

    def atom(self, name):
        world = name in ('world_uncertain','initial_ready','initial_blocked')
        if world or self.previous is None:
            features = (0.0,)*MENTAL_DIM
        else:
            event_goal = self.current['world']['goal_id']
            features = tuple(state_features(self.previous, event_goal, self.graphs, mental_only=True))
        key = (self.stage, world, features)
        if key not in self.context_keys:
            self.context_keys[key] = len(self.contexts)
            self.contexts.append(key)
        return Probability(1.0, ((self.context_keys[key],GATES.index(name),True),))

    def chance(self, name):
        return super().chance(name) if self.variant == 'A6' else self.atom(name)

    def transition(self, state, event):
        self.previous, self.current = state, event
        branches = super().transition(state,event)
        if self.stage < self.window_start:
            # A3 discards person memory, but keeps ALL factual world/contact replay.
            reset = []
            for new, probability in branches:
                goals = tuple(GoalState(g.goal_id,validity=g.validity,feasibility=g.feasibility,
                                       world_done=g.world_done,access=g.access,access_event=g.access_event,
                                       evidence=tuple(e for e in g.evidence if e[0] in 'VFA')) for g in new.goals)
                reset.append((JointState(goals),probability))
            return reset
        return branches


def compile_record(adapted, variant='A0', max_states=10000):
    model = TopologyModel(adapted,variant)
    state = model.initial(); goal = state.goal(model.target)
    ready,blocked = model.atom('initial_ready'),model.atom('initial_blocked')
    initial_states, initial_probs = [], []
    for label,p in [('READY',ready),('BLOCKED',(1-ready)*blocked),('UNKNOWN',(1-ready)*(1-blocked))]:
        initial_states.append(JointState(tuple(replace(g,feasibility=label) if g.goal_id==goal.goal_id else g for g in state.goals)))
        initial_probs.append(p)
    states, levels = initial_states, []
    for time,event in enumerate(adapted['events']):
        model.stage = time
        next_states, indices, edges = [], {}, []
        for old,state in enumerate(states):
            for new,probability in model.transition(state,event):
                if not probability:
                    continue
                if new not in indices:
                    indices[new] = len(next_states); next_states.append(new)
                if len(next_states)>max_states:
                    raise ValueError('NEURAL_STATE_BUDGET_EXCEEDED')
                edges.append((old,indices[new],probability))
        levels.append({'edges':edges,'states':next_states})
        states = next_states
    return {'input':adapted,'initial_states':initial_states,'initial_probs':initial_probs,
            'contexts':model.contexts,'levels':levels,'window_start':model.window_start}


def pack_probabilities(expressions, context_offset=0):
    coefficients,contexts,gates,positive,valid = [],[],[],[],[]
    length = max((len(x.factors) if isinstance(x,Probability) else 0 for x in expressions),default=0)
    length = max(1,length)
    for expression in expressions:
        p = expression if isinstance(expression,Probability) else Probability(expression)
        coefficients.append(p.coefficient)
        factors = list(p.factors)
        contexts.append([x[0]+context_offset for x in factors]+[0]*(length-len(factors)))
        gates.append([x[1] for x in factors]+[0]*(length-len(factors)))
        positive.append([x[2] for x in factors]+[True]*(length-len(factors)))
        valid.append([True]*len(factors)+[False]*(length-len(factors)))
    return (torch.tensor(coefficients,dtype=torch.float32),torch.tensor(contexts,dtype=torch.long),
            torch.tensor(gates,dtype=torch.long),torch.tensor(positive),torch.tensor(valid))


def probability_values(packed, gates):
    coefficient,contexts,slots,positive,valid = packed
    p = gates[contexts,slots]
    return coefficient*torch.where(valid,torch.where(positive,p,1-p),1.0).prod(dim=1)


class PackedTopology:
    """Disjoint union of sample lattices for batched index_add filtering."""
    def __init__(self, compiled):
        self.compiled, self.n = compiled, len(compiled)
        context_offsets, ctx_record, ctx_time, ctx_world, ctx_features = [],[],[],[],[]
        for record,item in enumerate(compiled):
            context_offsets.append(len(ctx_record))
            for time,world,features in item['contexts']:
                ctx_record.append(record);ctx_time.append(time);ctx_world.append(world);ctx_features.append(features)
        self.ctx_record = torch.tensor(ctx_record,dtype=torch.long)
        self.ctx_time = torch.tensor(ctx_time,dtype=torch.long)
        self.ctx_world = torch.tensor(ctx_world,dtype=torch.bool)
        self.ctx_features = torch.tensor(ctx_features,dtype=torch.float32)
        # Shift context references before packing all expressions.
        def shifted(expr,record):
            expr = expr if isinstance(expr,Probability) else Probability(expr)
            return Probability(expr.coefficient,tuple((c+context_offsets[record],g,s) for c,g,s in expr.factors))
        initials = [shifted(p,r) for r,c in enumerate(compiled) for p in c['initial_probs']]
        self.initial_probs = pack_probabilities(initials)
        states = [c['initial_states'] for c in compiled]
        self.levels = []
        for time in range(max(len(c['levels']) for c in compiled)):
            old_offset,new_offset,old,new,expressions,record_index,features,factors = 0,0,[],[],[],[],[],[]
            current_states = []
            for record,c in enumerate(compiled):
                if time<len(c['levels']):
                    level = c['levels'][time]
                else:
                    level = {'states':states[record], 'edges':[(i,i,1.0) for i in range(len(states[record]))]}
                old.extend(a+old_offset for a,_,_ in level['edges'])
                new.extend(b+new_offset for _,b,_ in level['edges'])
                expressions.extend(shifted(p,record) for _,_,p in level['edges'])
                for state in level['states']:
                    record_index.append(record)
                    features.append(state_features(state,c['input']['goal_id'],c['input']['observer_graphs']))
                    factors.append(factor_vector(state,c['input']['goal_id'],c['input']['observer_graphs']))
                current_states.append(level['states'])
                old_offset += len(states[record]);new_offset += len(level['states'])
            self.levels.append({'old':torch.tensor(old,dtype=torch.long),'new':torch.tensor(new,dtype=torch.long),
                                'probabilities':pack_probabilities(expressions),'size':new_offset,
                                'record':torch.tensor(record_index,dtype=torch.long),
                                'features':torch.tensor(features,dtype=torch.float32),
                                'factors':torch.tensor(factors,dtype=torch.float32)})
            states = current_states
        self.final_states = states

    def filter(self, gates):
        weights = probability_values(self.initial_probs,gates)
        marginals = []
        for level in self.levels:
            weights = torch.zeros(level['size']).index_add(
                0,level['new'],weights[level['old']]*probability_values(level['probabilities'],gates))
            total = torch.zeros(self.n).index_add(0,level['record'],weights)
            weights = weights/total[level['record']].clamp_min(1e-12)
            marginals.append(torch.zeros(self.n,FACTOR_DIM).index_add(
                0,level['record'],weights[:,None]*level['factors']))
        return weights,marginals
