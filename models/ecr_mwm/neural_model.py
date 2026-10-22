"""Shared components of the context model: input batches and frozen EC-JMF backbone.

The private backbone is not a separate supported training/deployment method.
Unused independent-head tensor keys are retained solely for C weight compatibility.
"""

import torch
from torch import nn
from torch.nn import functional as F

from models.ec_jmf.structured import resolve_person_event_goal
from models.ecr_mwm.p0_adapter import person_inputs
from models.ec_jmf.neural_filter import (PackedTopology,compile_record,probability_values,
                                       LABELS,OFFSETS,gate_names,factor_vector)
from models.ecr_mwm.neural_data import (event_features,state_features,WORLD_DIM,PERSON_DIM,
                                       MENTAL_DIM,STATE_DIM)


def mlp(inputs,hidden,outputs):
    return nn.Sequential(nn.Linear(inputs,hidden),nn.Tanh(),nn.Linear(hidden,outputs))


class Batch:
    def __init__(self, examples, variant='A0', semantic_contract='b-p0-v03/v3'):
        if variant != 'A0' or semantic_contract != 'b-p0-v03/v3':
            raise ValueError('CONTEXT_BACKBONE_REQUIRES_A0_V3')
        self.examples,self.variant = examples,variant
        self.semantic_contract = semantic_contract
        self.topology = PackedTopology([compile_record(x['input'],variant,semantic_contract=semantic_contract) for x in examples])
        self.n = len(examples)
        self.lengths = [len(x['input']['events']) for x in examples]
        self.length = max(self.lengths)
        self.world = torch.zeros(self.n,self.length,WORLD_DIM)
        self.person = torch.zeros(self.n,self.length,PERSON_DIM)
        self.visible = torch.zeros(self.n,self.length,dtype=torch.bool)
        self.carry = torch.zeros_like(self.visible)
        self.valid = torch.zeros_like(self.visible)
        self.regularizers = []
        for row,example in enumerate(examples):
            world,person,visible = event_features(example['input'],leak=False,semantic_contract=semantic_contract)
            length = len(world)
            self.world[row,:length] = torch.tensor(world)
            self.person[row,:length] = torch.tensor(person)
            self.visible[row,:length] = torch.tensor(visible)
            self.valid[row,:length] = True
            for time,event in enumerate(example['input']['events']):
                u = event['delivery']['comprehension']; kind=event['semantic']['kind']
                known = event['delivery']['access_evidence']=='ACCESSED'
                informational = kind not in ('none','interruption','nested_task_state')
                self.carry[row,time] = visible[time] and (known and (
                    not informational or u in ('UNDERSTOOD','MISUNDERSTOOD')))
                # Soft, input-derived event alignment; never a state_* label.
                if known and u in ('UNDERSTOOD','MISUNDERSTOOD') and event['world']['goal_id']==example['input']['goal_id']:
                    interpretation = event['semantic'].get('interpretation')
                    factor,label = None,None
                    if interpretation=='defer': factor,label='B','BELIEVES_VALID'
                    elif interpretation=='unresolved': factor,label='B','UNRESOLVED'
                    elif interpretation=='complete': factor,label='C','COMPLETED'
                    elif kind=='cancellation': factor,label='B','BELIEVES_INVALID'
                    elif kind=='completion_by_other': factor,label='C','COMPLETED'
                    elif kind=='commitment': factor,label='C',(('ACTIVE','SUSPENDED') if semantic_contract=='b-p0-v03/v3' else 'SUSPENDED')
                    elif kind=='abandonment': factor,label='C','ABANDONED'
                    if factor:
                        columns=([OFFSETS[factor][0]+LABELS[factor].index(item) for item in label]
                                 if isinstance(label,tuple) else OFFSETS[factor][0]+LABELS[factor].index(label))
                        self.regularizers.append((time,row,columns))
        self.info_pairs=[]
        for i,left in enumerate(examples):
            for j in range(i):
                right=examples[j]
                if (left.get('family') and left.get('family')==right.get('family') and
                    left['input']['observer_graphs']==right['input']['observer_graphs'] and
                    person_inputs(left['input'],semantic_contract)==person_inputs(right['input'],semantic_contract)):
                    self.info_pairs.append((j,i))
        self.final = self.topology.levels[-1]
        self.state_record = self.final['record']
        self.state_features = self.final['features']
        self.final_factors = self.final['factors']
        self._prepare_candidates(self.topology.final_states)

    def _prepare_candidates(self, states):
        candidates,mask = [],[]
        for row,group in enumerate(states):
            adapted = self.examples[row]['input']; target=adapted['goal_id'];graph=adapted['observer_graphs'][target]
            for state in group:
                g=state.goal(target); features=[]; valid=[]
                for position in range(8):
                    step=graph['steps'][position] if position<len(graph['steps']) else None
                    ready = step is not None and graph['dependencies'] is not None and set(graph['dependencies'].get(step,()))<=g.world_done
                    features.append([position/7,float(ready),float(step in g.known_steps),float(step==g.q)])
                    valid.append(step is not None and step not in g.world_done)
                candidates.append(features);mask.append(valid)
        self.candidates=torch.tensor(candidates,dtype=torch.float32)
        self.candidate_mask=torch.tensor(mask,dtype=torch.bool)



class _ECJMFBackbone(nn.Module):
    def __init__(self,variant='A0',hidden=24,semantic_contract='b-p0-v03/v3'):
        super().__init__()
        if variant != 'A0' or semantic_contract != 'b-p0-v03/v3':
            raise ValueError('CONTEXT_BACKBONE_REQUIRES_A0_V3')
        self.variant,self.hidden=variant,hidden
        self.semantic_contract = semantic_contract
        self.world_encoder=nn.GRUCell(WORLD_DIM,hidden)
        self.person_encoder=nn.GRUCell(PERSON_DIM,hidden)
        self.person_gates=mlp(hidden+MENTAL_DIM,hidden,len(gate_names(semantic_contract)))
        self.world_gates=mlp(hidden,hidden,len(gate_names(semantic_contract)))
        self.independent=nn.ModuleDict({factor:mlp(hidden,hidden,len(LABELS[factor])) for factor in 'BCQ'})
        self.resume_head=mlp(STATE_DIM,hidden,1)
        self.step_head=mlp(STATE_DIM+4,hidden,1)

    def encode(self,batch):
        world=torch.zeros(batch.n,self.hidden);person=torch.zeros_like(world)
        worlds,persons,memories=[],[],[]
        for time in range(batch.length):
            w=self.world_encoder(batch.world[:,time],world)
            world=torch.where(batch.valid[:,time,None],w,world)
            proposal=self.person_encoder(batch.person[:,time],person)
            persons.append(torch.where(batch.visible[:,time,None],proposal,person))
            person=torch.where(batch.carry[:,time,None],proposal,person)
            worlds.append(world);memories.append(person)
        return torch.stack(worlds,1),torch.stack(persons,1),torch.stack(memories,1)

    def forward(self,batch):
        if batch.semantic_contract != self.semantic_contract:
            raise ValueError("MODEL_BATCH_SEMANTIC_CONTRACT_MISMATCH")
        world,person,memory=self.encode(batch);top=batch.topology
        pc=person[top.ctx_record,top.ctx_time];wc=world[top.ctx_record,top.ctx_time]
        logits=torch.where(top.ctx_world[:,None],self.world_gates(wc),
                           self.person_gates(torch.cat((pc,top.ctx_features),-1)))
        gates=logits.sigmoid()
        weights,marginals=top.filter(gates)
        final=torch.zeros(batch.n,sum(len(x) for x in LABELS.values())).index_add(
            0,batch.state_record,weights[:,None]*batch.final_factors)
        hazard_logit=self.resume_head(batch.state_features).squeeze(-1)
        horizon=torch.tensor([e['input']['horizon']['value'] for e in batch.examples],dtype=torch.float32)
        resume=-torch.expm1(-horizon[batch.state_record]*F.softplus(hazard_logit))
        possible=batch.candidate_mask.any(-1)
        resume=resume*possible
        sf=batch.state_features[:,None,:].expand(-1,8,-1)
        step_logits=self.step_head(torch.cat((sf,batch.candidates),-1)).squeeze(-1)
        steps=step_logits.masked_fill(~batch.candidate_mask,-1e9).softmax(-1)*batch.candidate_mask
        mass=weights*resume
        p=torch.zeros(batch.n).index_add(0,batch.state_record,mass)
        qmass=torch.zeros(batch.n,8).index_add(0,batch.state_record,mass[:,None]*steps)
        q=qmass/p[:,None].clamp_min(1e-12)
        if batch.regularizers:
            consistency=torch.stack([-marginals[t][r,column].sum().clamp_min(1e-8).log()
                                     for t,r,column in batch.regularizers]).mean()
        else:
            consistency=p.sum()*0
        if batch.info_pairs:
            b0,b1=OFFSETS['B'];c0,c1=OFFSETS['C'];q0,q1=OFFSETS['Q']
            index=(batch.final_factors[:,b0:b1].argmax(-1)*50+
                   batch.final_factors[:,c0:c1].argmax(-1)*10+batch.final_factors[:,q0:q1].argmax(-1))
            joint=torch.zeros(batch.n*200).index_add(0,batch.state_record*200+index,weights).reshape(batch.n,200)
            divergences=[]
            for i,j in batch.info_pairs:
                a,b=joint[i],joint[j];mid=(a+b)/2
                divergences.append((a*(a.clamp_min(1e-12).log()-mid.clamp_min(1e-12).log())+
                                    b*(b.clamp_min(1e-12).log()-mid.clamp_min(1e-12).log())).sum()/2)
            invariance=torch.stack(divergences).mean()
        else: invariance=p.sum()*0
        return {'p':p,'q':q,'factors':final,'weights':weights,'marginals':marginals,
                'consistency':consistency,'invariance':invariance,'gates':gates}

    @torch.no_grad()
    def predict(self,batch,evidence=False):
        self.eval();out=self(batch);predictions=[]
        for row,e in enumerate(batch.examples):
            steps=e['input']['observer_graphs'][e['input']['goal_id']]['steps'];probability=max(0.0,min(1.0,float(out['p'][row])))
            t3={}
            for factor,labels in LABELS.items():
                values=out['factors'][row,slice(*OFFSETS[factor])].tolist()
                keys=steps+['UNKNOWN','NOT_APPLICABLE'] if factor=='Q' else labels
                if factor=='Q': values=values[:len(steps)]+values[8:]
                t3[factor]={k:v for k,v in zip(keys,values)}
            for distribution in t3.values():
                total=sum(distribution.values())
                for key in distribution: distribution[key]/=total
            qvalues=out['q'][row,:len(steps)].tolist()
            qtotal=sum(qvalues)
            predictions.append({'t1':probability,
                                't2':{s:v/qtotal for s,v in zip(steps,qvalues)} if qtotal>0 else None,
                                't3':t3})
        if evidence:
            for row,example in enumerate(batch.examples):
                trace=[];steps=example['input']['observer_graphs'][example['input']['goal_id']]['steps']
                for time,event in enumerate(example['input']['events']):
                    marginal=out['marginals'][time][row]
                    states={}
                    for factor,labels in LABELS.items():
                        vals=marginal[slice(*OFFSETS[factor])].tolist()
                        keys=steps+['UNKNOWN','NOT_APPLICABLE'] if factor=='Q' else labels
                        if factor=='Q': vals=vals[:len(steps)]+vals[8:]
                        states[factor]=dict(zip(keys,vals))
                    resolved=resolve_person_event_goal(event,example['input']['observer_graphs'],example['input']['goal_id'],self.semantic_contract)
                    trace.append({'event_id':event['event_id'],'delivery':event['delivery'],
                                  'source_goal_id':event['world']['goal_id'],'resolved_person_goal_id':resolved,
                                  'unassigned_information':event['semantic'] if resolved is None and event['delivery']['access_evidence']!='NOT_ACCESSED' else None,
                                  'state_after':states,'evidence_role':'conditioned_transition; no duplicate action likelihood'})
                predictions[row]['evidence_trace']=trace
        return predictions
