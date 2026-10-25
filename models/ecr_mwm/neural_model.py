"""P1-only neural EC-JMF: evidence encoders, joint transitions and filtering.

Text enters transition gates, not a substitute outcome classifier. The outcome
heads marginalize the filtered latent states. No pretrained state weights.
"""
from collections import defaultdict

import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence,pad_packed_sequence,pad_sequence

from models.ec_jmf.neural_filter import PackedTopology,compile_record,LABELS,OFFSETS,gate_names
from models.ecr_mwm.neural_data import (event_features,state_features,text_tokens,MAX_STEPS,
                                       EVENT_TYPES,WORLD_DIM,PERSON_DIM,MENTAL_DIM,STATE_DIM,CURRENT_UNDERSTANDING)

CONTRACT='p1-ec-jmf/v1'
WINDOWS=('single_response','assistant_turn','episode_tail','unobserved')


def mlp(inputs,hidden,outputs):
    return nn.Sequential(nn.Linear(inputs,hidden),nn.Tanh(),nn.Linear(hidden,outputs))


def word_bags(texts,index):
    words=[];offsets=[]
    for text in texts:
        offsets.append(len(words));words.extend(index.get(w,1) for w in text_tokens(text))
    return torch.tensor(words,dtype=torch.long),torch.tensor(offsets,dtype=torch.long)


class Batch:
    def __init__(self,examples,variant='A0',semantic_contract=CONTRACT,vocabulary=None):
        if semantic_contract!=CONTRACT: raise ValueError('P1_CONTRACT_REQUIRED')
        if not examples: raise ValueError('EMPTY_BATCH')
        self.examples,self.variant,self.semantic_contract=examples,variant,semantic_contract
        self.n=len(examples);self.lengths=[len(e['input']['events']) for e in examples]
        self.length=max(self.lengths)
        self.topology=PackedTopology([compile_record(e['input'],variant,semantic_contract=CONTRACT) for e in examples])
        self.world=torch.zeros(self.n,self.length,WORLD_DIM)
        self.person=torch.zeros(self.n,self.length,PERSON_DIM)
        self.visible=torch.zeros(self.n,self.length,dtype=torch.bool)
        self.valid=torch.zeros_like(self.visible)
        self.actions=defaultdict(list)
        self.window=torch.zeros(self.n,len(WINDOWS))
        world_text=[];person_text=[]
        for row,example in enumerate(examples):
            inputs=example['input'];events=inputs['events']
            w,p,v=event_features(inputs,leak=variant=='A1',semantic_contract=CONTRACT)
            length=len(events);self.world[row,:length]=torch.tensor(w);self.person[row,:length]=torch.tensor(p)
            self.visible[row,:length]=torch.tensor(v);self.valid[row,:length]=True
            start=self.topology.compiled[row]['window_start']
            if variant=='A3': self.visible[row,:start]=False;self.person[row,:start]=0
            self.window[row,WINDOWS.index(inputs['window']['kind'])]=1
            for time in range(self.length):
                if time>=length:
                    world_text.append('');person_text.append('');continue
                event=events[time]
                world_text.append((inputs.get('goal_text','')+' ' if time==0 else '')+event['world']['description'])
                text=event['world']['description'] if variant=='A1' else event.get('available_text','')
                person_text.append(text if bool(self.visible[row,time]) else '')
                own=event['person']
                if own and time>0:
                    step=own['step_id'];steps=inputs['observer_graphs'][inputs['goal_id']]['steps']
                    level=self.topology.compiled[row]['event_start_levels'][time]
                    self.actions[level].append((row,time,EVENT_TYPES.index(own['event_type']),steps.index(step) if step in steps else None))
        index={w:i for i,w in enumerate(vocabulary or ['<pad>','<unk>'])}
        self.world_words,self.world_offsets=word_bags(world_text,index)
        self.person_words,self.person_offsets=word_bags(person_text,index)
        self.carry=self.visible
        final=self.topology.levels[-1]
        self.state_record=final['record'];self.state_features=final['features'];self.final_factors=final['factors']
        candidates=[];mask=[]
        for row,states in enumerate(self.topology.final_states):
            inputs=examples[row]['input'];goal=inputs['goal_id'];steps=inputs['observer_graphs'][goal]['steps']
            for state in states:
                g=state.goal(goal);features=[];valid=[]
                for position in range(MAX_STEPS):
                    step=steps[position] if position<len(steps) else None
                    # Missing dependencies stay unknown; retries are legal P1 steps.
                    features.append([position/max(1,len(steps)-1),float(step in g.person_done),
                                     float(step in g.known_steps),float(step==g.q)])
                    valid.append(step is not None)
                candidates.append(features);mask.append(valid)
        self.candidates=torch.tensor(candidates,dtype=torch.float32)
        self.candidate_mask=torch.tensor(mask,dtype=torch.bool)
        # Runtime needs packed tensors and trace indices, not symbolic graph copies.
        self.topology.compiled=[{key:item[key] for key in ('event_levels','event_start_levels','window_start')}
                                for item in self.topology.compiled]
        del self.topology.final_states


class NeuralECJMF(nn.Module):
    def __init__(self,variant='A0',hidden=24,semantic_contract=CONTRACT,vocabulary_size=2):
        super().__init__()
        if semantic_contract!=CONTRACT: raise ValueError('P1_CONTRACT_REQUIRED')
        self.variant,self.hidden,self.semantic_contract=variant,hidden,semantic_contract
        self.vocabulary_size=vocabulary_size
        self.world_text=nn.EmbeddingBag(vocabulary_size,32,mode='mean',padding_idx=0)
        self.person_text=nn.EmbeddingBag(vocabulary_size,32,mode='mean',padding_idx=0)
        self.world_projection=nn.Linear(32,WORLD_DIM,bias=False)
        self.person_projection=nn.Linear(32,PERSON_DIM,bias=False)
        self.world_encoder=nn.GRU(WORLD_DIM,hidden,batch_first=True)
        self.person_encoder=nn.GRU(PERSON_DIM,hidden,batch_first=True)
        self.person_gates=mlp(hidden+MENTAL_DIM,hidden,len(gate_names(CONTRACT)))
        self.world_gates=mlp(hidden,hidden,len(gate_names(CONTRACT)))
        self.resume_head=mlp(STATE_DIM+len(WINDOWS),hidden,1)
        self.step_head=mlp(STATE_DIM+4,hidden,1)
        self.event_head=mlp(MENTAL_DIM+hidden,hidden,len(EVENT_TYPES)+MAX_STEPS)
        if variant=='A6':
            self.person_gates.requires_grad_(False);self.world_gates.requires_grad_(False)

    def encode(self,batch):
        wt=self.world_projection(self.world_text(batch.world_words,batch.world_offsets)).reshape(batch.n,batch.length,-1)
        pt=self.person_projection(self.person_text(batch.person_words,batch.person_offsets)).reshape(batch.n,batch.length,-1)
        world_input=pack_padded_sequence(batch.world+wt,batch.lengths,batch_first=True,enforce_sorted=False)
        world,_=self.world_encoder(world_input)
        world,_=pad_packed_sequence(world,batch_first=True,total_length=batch.length)
        visible_counts=batch.visible.sum(1)
        personal=[(batch.person[row]+pt[row])[batch.visible[row]] if visible_counts[row] else
                  torch.zeros(1,PERSON_DIM) for row in range(batch.n)]
        padded=pad_sequence(personal,batch_first=True)
        packed=pack_padded_sequence(padded,visible_counts.clamp_min(1).cpu(),batch_first=True,enforce_sorted=False)
        encoded,_=self.person_encoder(packed)
        encoded,_=pad_packed_sequence(encoded,batch_first=True)
        encoded=torch.cat((torch.zeros(batch.n,1,self.hidden),encoded),1)
        indices=batch.visible.long().cumsum(1)
        person=encoded[torch.arange(batch.n)[:,None],indices]
        return world,person,person

    def causal_consistency(self,batch,priors,memory):
        losses=[]
        for time,targets in batch.actions.items():
            weights,rows,features=priors[time]
            active=torch.zeros(batch.n,dtype=torch.bool)
            active[[r for r,_,_,_ in targets]]=True
            select=active[rows];r=rows[select];w=weights[select]
            source_times=torch.zeros(batch.n,dtype=torch.long)
            for row,source_time,_,_ in targets: source_times[row]=source_time
            past=memory[r,source_times[r]-1]  # Strictly before each ORIGINAL event.
            logits=self.event_head(torch.cat((features[select,:MENTAL_DIM],past),-1))
            types=logits[:,:len(EVENT_TYPES)].softmax(-1)
            type_probs=torch.zeros(batch.n,len(EVENT_TYPES)).index_add(0,r,w[:,None]*types)
            step_logits=logits[:,len(EVENT_TYPES):]
            lengths=torch.tensor([len(e['input']['observer_graphs'][e['input']['goal_id']]['steps']) for e in batch.examples])
            possible=torch.arange(MAX_STEPS)[None,:]<lengths[r,None]
            steps=step_logits.masked_fill(~possible,-1e9).softmax(-1)
            step_probs=torch.zeros(batch.n,MAX_STEPS).index_add(0,r,w[:,None]*steps)
            for row,_,kind,step in targets:
                losses.append(-type_probs[row,kind].clamp_min(1e-12).log())
                if step is not None: losses.append(-step_probs[row,step].clamp_min(1e-12).log())
        return torch.stack(losses).mean() if losses else memory.sum()*0

    def forward(self,batch,trace=False):
        if batch.semantic_contract!=self.semantic_contract: raise ValueError('MODEL_BATCH_CONTRACT_MISMATCH')
        world,person,memory=self.encode(batch);top=batch.topology
        pc=person[top.ctx_record,top.ctx_time];wc=world[top.ctx_record,top.ctx_time]
        logits=torch.where(top.ctx_world[:,None],self.world_gates(wc),
                           self.person_gates(torch.cat((pc,top.ctx_features),-1)))
        gates=logits.sigmoid()
        filtered=top.filter(gates,return_priors=True,return_understanding=trace,trace=trace)
        weights,marginals,priors=filtered[:3];understanding=filtered[3] if trace else []
        final=torch.zeros(batch.n,sum(len(v) for v in LABELS.values())).index_add(
            0,batch.state_record,weights[:,None]*batch.final_factors)
        features=torch.cat((batch.state_features,batch.window[batch.state_record]),-1)
        resume=self.resume_head(features).squeeze(-1).sigmoid()*batch.candidate_mask.any(-1)
        sf=batch.state_features[:,None,:].expand(-1,MAX_STEPS,-1)
        step_logits=self.step_head(torch.cat((sf,batch.candidates),-1)).squeeze(-1)
        steps=step_logits.masked_fill(~batch.candidate_mask,-1e9).softmax(-1)*batch.candidate_mask
        mass=weights*resume
        p=torch.zeros(batch.n).index_add(0,batch.state_record,mass)
        qmass=torch.zeros(batch.n,MAX_STEPS).index_add(0,batch.state_record,mass[:,None]*steps)
        q=qmass/p[:,None].clamp_min(1e-12)
        consistency=(self.causal_consistency(batch,priors,memory)
                     if self.training and self.variant!='A4' else p.sum()*0)
        return {'p':p,'q':q,'factors':final,'weights':weights,'marginals':marginals,
                'consistency':consistency,'invariance':p.sum()*0,'gates':gates,
                'event_targets':sum(len(v) for v in batch.actions.values()),
                'understanding_marginals':understanding,
                'understanding':torch.zeros(batch.n,len(CURRENT_UNDERSTANDING)).index_add(0,batch.state_record,weights[:,None]*top.levels[-1]['understanding']),
                'initial_understanding':torch.zeros(batch.n,len(CURRENT_UNDERSTANDING)).index_add(0,top.initial_record,top.initial_understanding),
                'initial_factors':torch.zeros(batch.n,sum(len(v) for v in LABELS.values())).index_add(0,top.initial_record,top.initial_factors)}

    @torch.no_grad()
    def predict(self,batch,evidence=False):
        self.eval();out=self(batch,trace=evidence);predictions=[]
        scope={factor:('Observed-label supervision only where the P1 source mask enables V.'
                       if factor=='V' else 'Latent diagnostic; no direct P1 state-label supervision.')
               for factor in (*LABELS,'U')}
        def factor_distribution(values,factor,steps):
            values=values[slice(*OFFSETS[factor])].tolist()
            keys=LABELS[factor]
            if factor=='Q':
                keys=steps+['UNKNOWN','NOT_APPLICABLE']
                values=values[:len(steps)]+values[MAX_STEPS:]
            total=sum(values)
            return {k:v/max(total,1e-12) for k,v in zip(keys,values)}
        for row,e in enumerate(batch.examples):
            steps=e['input']['observer_graphs'][e['input']['goal_id']]['steps']
            t3={factor:factor_distribution(out['factors'][row],factor,steps) for factor in LABELS}
            u=out['understanding'][row]
            probability=max(0.0,min(1.0,float(out['p'][row])))
            distribution=out['q'][row,:len(steps)].tolist();total=sum(distribution)
            pred={'t1':probability if steps else None,'t2':{s:v/total for s,v in zip(steps,distribution)} if total else None,
                  't3':t3,'understanding':dict(zip(CURRENT_UNDERSTANDING,u.tolist())),
                  'state_supervision_scope':scope,'window':e['input']['window'],
                  'latent_state_warning':'Only masked V has direct P1 state supervision; F/A/B/C/Q/U are latent diagnostics.'}
            if evidence:
                trace=[]
                for time,event in enumerate(e['input']['events']):
                    level=batch.topology.compiled[row]['event_levels'][time]
                    factors=out['marginals'][level][row] if level>=0 else out['initial_factors'][row]
                    u=out['understanding_marginals'][level][row] if level>=0 else out['initial_understanding'][row]
                    trace.append({'event_id':event['event_id'],'access':event['delivery']['access_evidence'],
                        'observed_understanding':event['delivery']['comprehension'],
                        'understanding_marginal':dict(zip(CURRENT_UNDERSTANDING,u.tolist())),
                        'factor_marginals':{f:factor_distribution(factors,f,steps) for f in LABELS},
                        'state_supervision_scope':scope,
                        'role':'conditioned transition; merged hypotheses, not a representative path'})
                pred['evidence_trace']=trace
            predictions.append(pred)
        return predictions


_ECJMFBackbone=NeuralECJMF
