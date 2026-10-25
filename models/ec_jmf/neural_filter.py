"""Differentiable finite EC-JMF topology; probabilities are rebuilt by PyTorch.

Only states/edges and references to named gates are cached. No labels or learned
predictions enter compilation. Restores the original A0--A6 neural topology.
"""
from dataclasses import replace
from itertools import product

import torch

from models.ec_jmf.structured import StructuredModel, GoalState, JointState, Mechanisms
from models.ecr_mwm.neural_data import state_features, MENTAL_DIM, MAX_STEPS, CURRENT_UNDERSTANDING

GATES = ('access_uncertain', 'understanding_uncertain', 'accept_message',
         'invalid_abandon', 'action_validity', 'world_uncertain', 'recall_next',
         'initial_ready', 'initial_blocked')
P1_GATES = ('access_uncertain','understanding_uncertain','misunderstanding_uncertain',
            'accept_message','belief_valid','belief_invalid','belief_unresolved',
            'invalid_abandon','action_validity','world_keep','world_valid','world_cancel','world_fulfill')

def gate_names(semantic_contract):
    if semantic_contract == 'p1-ec-jmf/v1': return P1_GATES
    if semantic_contract == 'legacy-v1': return GATES
    if semantic_contract == 'b-p0-v03/v2': return GATES + ('recommit_goal',)
    if semantic_contract == 'b-p0-v03/v3': return GATES + ('reengage_goal',)
    raise ValueError('UNKNOWN_SEMANTIC_CONTRACT')


LABELS = {'V':('VALID','CANCELLED','FULFILLED','UNKNOWN'),
          'F':('READY','BLOCKED','UNKNOWN'), 'A':('ACCESSED','NOT_ACCESSED','UNCERTAIN'),
          'B':('BELIEVES_VALID','BELIEVES_INVALID','UNRESOLVED','UNKNOWN'),
          'C':('ACTIVE','SUSPENDED','ABANDONED','COMPLETED','UNKNOWN'),
          'Q':tuple(f'k{i}' for i in range(MAX_STEPS))+('UNKNOWN','NOT_APPLICABLE')}
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


def understanding_vector(state, target):
    history = state.goal(target).understanding
    label = history[-1][-1] if history else 'UNKNOWN'
    if label not in CURRENT_UNDERSTANDING:
        label = 'UNKNOWN'
    return [float(label == item) for item in CURRENT_UNDERSTANDING]


class TopologyModel(StructuredModel):
    def __init__(self, adapted, variant, semantic_contract):
        mechanisms = Mechanisms(access_gate=variant!='A1', comprehension_gate=variant!='A1',
                                learned_gates=variant!='A6')
        super().__init__(adapted, mechanisms=mechanisms, semantic_contract=semantic_contract)
        self.variant = variant
        self.contexts, self.context_keys = [], {}
        self.stage, self.previous = 0, None
        visible = [i for i,e in enumerate(adapted['events']) if e['person'] or e.get('available_text')]
        self.window_start = visible[-5] if variant == 'A3' and len(visible)>5 else 0

    def atom(self, name):
        world = name.startswith('world_') or name in ('initial_ready','initial_blocked')
        if world or self.previous is None:
            features = (0.0,)*MENTAL_DIM
        else:
            event_goal = self.current['world']['goal_id']
            features = tuple(state_features(self.previous, event_goal, self.graphs, mental_only=True))
        key = (self.stage, world, features)
        if key not in self.context_keys:
            self.context_keys[key] = len(self.contexts)
            self.contexts.append(key)
        return Probability(1.0, ((self.context_keys[key],gate_names(self.semantic_contract).index(name),True),))

    def chance(self, name):
        return super().chance(name) if self.variant == 'A6' else self.atom(name)

    def transition(self,state,event):
        self.previous,self.current=state,event
        if self.semantic_contract=='p1-ec-jmf/v1':
            if self.variant=='A3' and self.stage<self.window_start and self.phase!=0:
                branches=[(state,1.0)]
            else:
                branches=self.p1_phase(state,event,self.phase)
            if self.variant=='A3' and self.stage<self.window_start and self.phase==3:
                reset=[]
                for new,p in branches:
                    goals=tuple(GoalState(g.goal_id,validity=g.validity,feasibility=g.feasibility,
                                         world_done=g.world_done,access=g.access) for g in new.goals)
                    reset.append((JointState(goals),p))
                return reset
            return branches
        return super().transition(state,event)


def compile_record(adapted,variant='A0',max_states=10000,semantic_contract='p1-ec-jmf/v1'):
    model=TopologyModel(adapted,variant,semantic_contract)
    state=model.initial();initial_states=[state];initial_probs=[1.0]
    states=initial_states;levels=[];event_levels=[];event_start_levels=[]
    for time,event in enumerate(adapted['events']):
        model.stage=time;event_start_levels.append(len(levels))
        phases=range(4) if semantic_contract=='p1-ec-jmf/v1' else (0,)
        for phase in phases:
            model.phase=phase
            next_states=[];indices={};edges=[]
            for old,state in enumerate(states):
                for new,probability in model.transition(state,event):
                    if not probability: continue
                    if new not in indices:
                        indices[new]=len(next_states);next_states.append(new)
                    if len(next_states)>max_states: raise ValueError('NEURAL_STATE_BUDGET_EXCEEDED')
                    edges.append((old,indices[new],probability))
            identity=(len(next_states)==len(states) and len(edges)==len(states) and
                      all(a==b and not isinstance(p,Probability) and p==1.0 for a,b,p in edges) and next_states==states)
            retain_action=(phase==3 and bool(event['person']))
            project=(variant=='A2' and phase==3 and (not identity or len(levels)>event_start_levels[-1]))
            if identity and not retain_action and not project:
                continue
            if project:
                original=next_states;next_states=independent_support(original,model.target)
                index={state:i for i,state in enumerate(next_states)}
                edges=[(a,index[original[b]],p) for a,b,p in edges]
            if len(next_states)>max_states: raise ValueError('NEURAL_STATE_BUDGET_EXCEEDED')
            levels.append({'edges':edges,'states':next_states,'source_time':time,'phase':phase,'project':project})
            states=next_states
        event_levels.append(len(levels)-1)
    return {'input':adapted,'initial_states':initial_states,'initial_probs':initial_probs,
            'contexts':model.contexts,'levels':levels,'window_start':model.window_start,
            'variant':variant,'target':model.target,'semantic_contract':semantic_contract,
            'event_levels':event_levels,'event_start_levels':event_start_levels}



def non_bcq_key(state,target):
    goal=state.goal(target)
    neutral=replace(goal,belief='UNKNOWN',commitment='UNKNOWN',q='UNKNOWN')
    return JointState(tuple(neutral if g.goal_id==target else g for g in state.goals),state.stack)


def independent_support(states,target):
    groups={}
    for state in states:
        key=non_bcq_key(state,target)
        if key not in groups: groups[key]=[state,set(),set(),set()]
        entry=groups[key];g=state.goal(target)
        entry[1].add(g.belief);entry[2].add(g.commitment);entry[3].add(g.q)
    expanded=[]
    for representative,bs,cs,qs in groups.values():
        for b,c,q in product(sorted(bs),sorted(cs),sorted(qs)):
            goal=replace(representative.goal(target),belief=b,commitment=c,q=q)
            expanded.append(JointState(tuple(goal if g.goal_id==target else g for g in representative.goals),representative.stack))
    return expanded


def projection_indices(states_by_record,compiled):
    groups={};group=[];bs=[];cs=[];qs=[]
    for record,states in enumerate(states_by_record):
        target=compiled[record]['target']
        for state in states:
            key=(record,non_bcq_key(state,target))
            if key not in groups: groups[key]=len(groups)
            goal=state.goal(target)
            group.append(groups[key]);bs.append(LABELS['B'].index(goal.belief))
            cs.append(LABELS['C'].index(goal.commitment));qs.append(LABELS['Q'].index(q_label(goal,compiled[record]['input']['observer_graphs'])))
    return (torch.tensor(group),torch.tensor(bs),torch.tensor(cs),torch.tensor(qs),len(groups))


def independent_projection(weights,indices):
    group,bs,cs,qs,n=indices
    mass=torch.zeros(n).index_add(0,group,weights)
    result=mass[group]
    for slots,size in ((bs,len(LABELS['B'])),(cs,len(LABELS['C'])),(qs,len(LABELS['Q']))):
        probs=torch.zeros(n*size).index_add(0,group*size+slots,weights).reshape(n,size)
        probs=probs/mass[:,None].clamp_min(1e-12)
        result=result*probs[group,slots]
    return result


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
    if gates.shape[0]==0:
        if bool(valid.any()): raise ValueError('MISSING_GATE_CONTEXT')
        return coefficient
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
        self.ctx_features = torch.tensor(ctx_features,dtype=torch.float32).reshape(-1,MENTAL_DIM)
        # Shift context references before packing all expressions.
        def shifted(expr,record):
            expr = expr if isinstance(expr,Probability) else Probability(expr)
            return Probability(expr.coefficient,tuple((c+context_offsets[record],g,s) for c,g,s in expr.factors))
        initials = [shifted(p,r) for r,c in enumerate(compiled) for p in c['initial_probs']]
        self.initial_probs = pack_probabilities(initials)
        states = [c['initial_states'] for c in compiled]
        self.initial_record=torch.tensor([r for r,c in enumerate(compiled) for _ in c['initial_states']])
        self.initial_features=torch.tensor([state_features(s,c['input']['goal_id'],c['input']['observer_graphs']) for c in compiled for s in c['initial_states']],dtype=torch.float32)
        self.initial_factors=torch.tensor([factor_vector(s,c['input']['goal_id'],c['input']['observer_graphs']) for c in compiled for s in c['initial_states']],dtype=torch.float32)
        self.initial_understanding=torch.tensor([understanding_vector(s,c['input']['goal_id']) for c in compiled for s in c['initial_states']],dtype=torch.float32)
        self.levels = []
        for time in range(max(len(c['levels']) for c in compiled)):
            old_offset,new_offset,old,new,expressions,record_index,features,factors = 0,0,[],[],[],[],[],[]
            current_states = []; understanding=[]
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
                    understanding.append(understanding_vector(state,c['input']['goal_id']))
                current_states.append(level['states'])
                old_offset += len(states[record]);new_offset += len(level['states'])
            self.levels.append({'old':torch.tensor(old,dtype=torch.long),'new':torch.tensor(new,dtype=torch.long),
                                'probabilities':pack_probabilities(expressions),'size':new_offset,
                                'record':torch.tensor(record_index,dtype=torch.long),
                                'features':torch.tensor(features,dtype=torch.float32),
                                'factors':torch.tensor(factors,dtype=torch.float32),
                                'understanding':torch.tensor(understanding,dtype=torch.float32)})
            if compiled[0].get('variant')=='A2':
                # Each disjoint record projects only at its original event end.
                active=[time<len(c['levels']) and c['levels'][time].get('project',False) for c in compiled]
                if any(active): self.levels[-1]['projection']=(projection_indices(current_states,compiled),torch.tensor(active)[self.levels[-1]['record']])
            states = current_states
        self.final_states = states

    def filter(self, gates, return_priors=False, return_understanding=False, trace=True):
        weights = probability_values(self.initial_probs,gates)
        marginals = []; priors=[]; understanding=[]
        previous_record,previous_features=self.initial_record,self.initial_features
        for level in self.levels:
            if return_priors: priors.append((weights,previous_record,previous_features))
            weights = torch.zeros(level['size']).index_add(
                0,level['new'],weights[level['old']]*probability_values(level['probabilities'],gates))
            total = torch.zeros(self.n).index_add(0,level['record'],weights)
            weights = weights/total[level['record']].clamp_min(1e-12)
            if 'projection' in level:
                indices,mask=level['projection']
                weights=torch.where(mask,independent_projection(weights,indices),weights)
            if trace:
                marginals.append(torch.zeros(self.n,FACTOR_DIM).index_add(
                    0,level['record'],weights[:,None]*level['factors']))
            if return_understanding:
                understanding.append(torch.zeros(self.n,len(CURRENT_UNDERSTANDING)).index_add(
                    0,level['record'],weights[:,None]*level['understanding']))
            previous_record,previous_features=level['record'],level['features']
        result=(weights,marginals,priors) if return_priors else (weights,marginals)
        return result+(understanding,) if return_understanding else result
