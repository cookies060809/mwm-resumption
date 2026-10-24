"""READY two-task model: frozen structured EC-JMF plus learned response decoder.

The response encoder/decoder never writes to the structured mental-state filter.
"""
from collections import Counter
import io
import math
import re

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence
from torch.nn import functional as F

from models.ecr_mwm.context_residual import ContextECJMF
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.ready_data import source_tokens, tokens, state_input

FORMAT='a-ready-ec-jmf/v1'


class ResponseDecoder(nn.Module):
    def __init__(self, size, embedding=64, hidden=96):
        super().__init__()
        self.embedding=nn.Embedding(size,embedding,padding_idx=0)
        self.encoder=nn.GRU(embedding,hidden,batch_first=True)
        self.decoder=nn.GRU(embedding,hidden,batch_first=True)
        self.output=nn.Linear(hidden*2,size)
        self.hidden=hidden

    def encode(self, source):
        lengths=source.ne(0).sum(-1)
        packed=pack_padded_sequence(self.embedding(source),lengths.cpu(),batch_first=True,enforce_sorted=False)
        encoded, memory=self.encoder(packed)
        encoded,_=pad_packed_sequence(encoded,batch_first=True,total_length=source.shape[1])
        return encoded,memory,source.eq(0)

    def project(self, decoded, encoded, mask):
        score=torch.bmm(decoded,encoded.transpose(1,2))/math.sqrt(self.hidden)
        attention=score.masked_fill(mask[:,None,:],-1e9).softmax(-1)
        return self.output(torch.cat((decoded,torch.bmm(attention,encoded)),-1))

    def forward(self, source, decoder_input):
        encoded,memory,mask=self.encode(source)
        decoded,_=self.decoder(self.embedding(decoder_input),memory)
        return self.project(decoded,encoded,mask)

    @torch.no_grad()
    def generate(self, source, limit):
        self.eval()
        encoded,memory,mask=self.encode(source)
        current=torch.full((source.shape[0],1),2,dtype=torch.long)
        done=torch.zeros(source.shape[0],dtype=torch.bool)
        sequences=[[] for _ in range(source.shape[0])]
        for _ in range(limit):
            decoded,memory=self.decoder(self.embedding(current),memory)
            logits=self.project(decoded,encoded,mask)[:,0]
            logits[:,[0,2,4,5,6,7]]=-torch.inf  # never emit padding/BOS/role markers
            next_token=logits.argmax(-1)
            for row,value in enumerate(next_token.tolist()):
                if not done[row]: sequences[row].append(value)
            done |= next_token.eq(3)
            current=next_token[:,None]
            if bool(done.all()): break
        return sequences


class ReadyModel(nn.Module):
    def __init__(self, context_architecture, vocabulary, config):
        super().__init__()
        self.context=ContextECJMF(**context_architecture)
        self.context.requires_grad_(False)
        self.vocabulary=vocabulary
        self.index={word:i for i,word in enumerate(vocabulary)}
        self.config=config
        self.response=ResponseDecoder(len(vocabulary),**config['architecture'])

    def ids(self, words):
        return [self.index.get(word,1) for word in words]

    def source_batch(self, inputs):
        return pad_sequence([torch.tensor(self.ids(source_tokens(inp,self.config['encoding'])[0]),dtype=torch.long)
                             for inp in inputs],batch_first=True,padding_value=0)

    def training_batch(self, rows):
        source=self.source_batch([r['input'] for r in rows])
        labels=[self.ids(tokens(r['target']))+[3] for r in rows]
        target=pad_sequence([torch.tensor(t,dtype=torch.long) for t in labels],batch_first=True,padding_value=0)
        previous=pad_sequence([torch.tensor([2]+t[:-1],dtype=torch.long) for t in labels],batch_first=True,padding_value=0)
        return source,previous,target

    def loss_sum(self, rows):
        source,previous,target=self.training_batch(rows)
        logits=self.response(source,previous)
        return F.cross_entropy(logits.reshape(-1,len(self.vocabulary)),target.reshape(-1),ignore_index=0,reduction='sum'),int(target.ne(0).sum())

    @torch.no_grad()
    def predict(self, task, inputs):
        self.eval()
        if task=='state_inference':
            # READY state examples have no horizon contract: expose T3 only.
            adapted=[{'input':state_input(inp)} for inp in inputs]
            return [{'task':task,'state_distributions':p['t3'],'T1':None,'T2':None}
                    for p in self.context.predict(Batch(adapted))]
        if task!='interruption_response': raise ValueError('UNKNOWN_READY_TASK')
        generated=self.response.generate(self.source_batch(inputs),self.config['max_generated_tokens'])
        results=[]
        for sequence in generated:
            words=[self.vocabulary[t] for t in sequence if t!=3]
            text=' '.join(words)
            text=re.sub(r'\s+([.,!?;:])',r'\1',text)
            results.append({'task':task,'response':text,'tokens':words,'ended_with_eos':bool(sequence and sequence[-1]==3),
                            'state_distributions':None,'T1':None,'T2':None})
        return results


def checkpoint_bytes(model, metadata):
    buffer=io.BytesIO()
    torch.save({'format':FORMAT,'context_architecture':model.context.architecture,
                'vocabulary':model.vocabulary,'config':model.config,'metadata':metadata,
                'state_dict':{k:v.detach().cpu().clone() for k,v in model.state_dict().items()}},buffer)
    return buffer.getvalue()


def reload_model(payload):
    state=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    if state['format']!=FORMAT: raise ValueError('READY_MODEL_FORMAT_REQUIRED')
    model=ReadyModel(state['context_architecture'],state['vocabulary'],state['config'])
    model.load_state_dict(state['state_dict'],strict=True)
    model.eval()
    return model


def token_f1(predicted, reference):
    overlap=sum((Counter(predicted)&Counter(reference)).values())
    return 2*overlap/(len(predicted)+len(reference)) if predicted or reference else 1.0
