"""Complete visible-context EC-JMF model, ported from Bill_method 291e94a.

All backbone weights are included in the model checkpoint. No old model file,
C evaluation package or inference-only wrapper is needed.
"""
from torch import nn
import torch

from models.ecr_mwm.neural_data import STATE_DIM
from models.ecr_mwm.neural_model import _ECJMFBackbone

FORMAT = "a-context-ec-jmf/v1"


class ContextHazard(nn.Module):
    def __init__(self, base_head, hidden=24, bound=2.0, dropout=0.1):
        super().__init__()
        self.base_head = base_head
        self.attention = nn.Linear(hidden, 1, bias=False)
        self.residual = nn.Sequential(
            nn.Linear(STATE_DIM + hidden * 2, hidden), nn.Tanh(),
            nn.Dropout(dropout), nn.Linear(hidden, 1))
        nn.init.zeros_(self.residual[-1].weight)
        nn.init.zeros_(self.residual[-1].bias)
        self.bound = bound
        self.context = None
        self.records = None

    def set_context(self, proposals, memories, batch):
        mask = batch.valid & batch.visible
        scores = self.attention(proposals).squeeze(-1).masked_fill(~mask, -1e9)
        weights = scores.softmax(-1) * mask
        weights = weights / weights.sum(-1, keepdim=True).clamp_min(1e-12)
        pooled = (proposals * weights[..., None]).sum(1)
        self.context = torch.cat((pooled, memories[:, -1]), -1)
        self.records = batch.state_record

    def forward(self, features):
        if self.context is None:
            raise RuntimeError("Context must be set by the same forward call")
        extra = self.context[self.records]
        delta = self.bound * torch.tanh(self.residual(torch.cat((features, extra), -1)))
        return self.base_head(features) + delta


class ContextECJMF(_ECJMFBackbone):
    def __init__(self, hidden=24, semantic_contract='b-p0-v03/v3', bound=2.0, dropout=0.1):
        super().__init__('A0', hidden, semantic_contract)
        self.requires_grad_(False)
        self.resume_head = ContextHazard(self.resume_head, hidden, bound, dropout)
        self.architecture = dict(hidden=hidden, semantic_contract=semantic_contract,
                                 bound=bound, dropout=dropout)

    def encode(self, batch):
        world, proposals, memories = super().encode(batch)
        self.resume_head.set_context(proposals, memories, batch)
        return world, proposals, memories


def initialize_context(checkpoint, seed):
    """Reinitialize C's context module on the frozen backbone, without an old file.

    C consumed RNG for two backbone constructions before context initialization.
    Keep that order so replay does not silently change its initialization protocol.
    """
    from models.ecr_mwm.neural_training import seed_everything
    seed_everything(seed, 1)
    architecture = checkpoint['architecture']
    _ECJMFBackbone('A0', architecture['hidden'], architecture['semantic_contract'])
    model = ContextECJMF(**architecture)
    state = model.state_dict()
    for name, value in checkpoint['state_dict'].items():
        if not name.startswith(('resume_head.attention.', 'resume_head.residual.')):
            state[name] = value
    model.load_state_dict(state, strict=True)
    model.eval()
    return model
