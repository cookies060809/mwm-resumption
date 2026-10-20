"""Selected model-independent constraints; no provisional event schema."""

def validate_graph(steps, dependencies):
    if len(steps) != len(set(steps)) or any(not isinstance(s, str) or not s for s in steps):
        raise ValueError('INVALID_STEP_IDS')
    known = set(steps)
    if set(dependencies) - known:
        raise ValueError('DANGLING_DEPENDENCY')
    for parents in dependencies.values():
        if set(parents) - known:
            raise ValueError('DANGLING_DEPENDENCY')
    remaining = set(steps)
    while remaining:
        available = {s for s in remaining if not (set(dependencies.get(s, ())) & remaining)}
        if not available:
            raise ValueError('CYCLIC_TASK_GRAPH')
        remaining -= available


def supervision_masks(observed_resume, window_complete, observed_step=None, state_evidence=None):
    if observed_resume is not None and type(observed_resume) is not bool:
        raise ValueError('INVALID_RESUME_LABEL')
    if type(window_complete) is not bool:
        raise ValueError('INVALID_WINDOW_COVERAGE')
    resume_valid = observed_resume is True or (observed_resume is False and window_complete)
    return {'resume': resume_valid,
            'step': observed_resume is True and observed_step is not None,
            'state': {factor: bool(supported) for factor, supported in (state_evidence or {}).items()}}
