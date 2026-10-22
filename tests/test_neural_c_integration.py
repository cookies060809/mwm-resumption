"""Real neural training, serialization and label-free C protocol boundaries."""
import copy
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from integration.a_neural_output import normalize_neural_output
from models.ecr_mwm.neural_data import load_records
from models.ecr_mwm.neural_model import Batch, NeuralECJMF
from models.ecr_mwm.neural_training import fit_one, reload_model, seed_everything
from mwm_eval.p0 import prepare_dataset
from mwm_eval.metrics import evaluate
from mwm_eval.schema import validate_prediction
from scripts.run_neural_p0_evaluation import state_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('contract', ['legacy-v1', 'b-p0-v03/v3'])
def test_neural_checkpoint_actually_trains_and_reloads_into_C(contract):
    config = json.loads((ROOT / "configs/a_neural_p0.json").read_text(encoding="utf-8"))
    config["epochs"] = 1
    config['semantic_contract'] = contract
    examples = load_records(ROOT / "data/p0/v0.3/p0_samples.json")
    seed_everything(0)
    train = Batch([e for e in examples if e["split"] == "train"][:2], semantic_contract=contract)
    dev = Batch([e for e in examples if e["split"] == "dev"][:2], semantic_contract=contract)
    payload, audit = fit_one(train, dev, "A0", 0, config)
    assert audit["first_epoch_audit"]["nonzero_gradient_parameters"] > 0
    assert audit["reload_max_abs_error"] == 0
    repeated, _ = fit_one(train, dev, "A0", 0, config)
    assert state_hash(payload) == state_hash(repeated)
    raw = json.loads((ROOT / "data/p0/v0.3/p0_samples.json").read_text(encoding="utf-8"))
    records, _ = prepare_dataset(raw)
    obs = next(r["observation"] for r in records if r["split"] == "test")
    batch = Batch([{"input": obs["structured_evidence"]}], semantic_contract=contract)
    native = reload_model(payload).predict(batch, evidence=True)[0]
    prediction = normalize_neural_output(native, obs)
    validate_prediction(prediction, obs)
    assert prediction["p_resume"] == native["t1"]
    assert prediction["state_probs"] == native["t3"]
    assert prediction["metadata"]["a_evidence_trace"]


def test_aligned_model_rejects_legacy_batch():
    examples = load_records(ROOT / 'data/p0/v0.3/p0_samples.json')
    model = NeuralECJMF(semantic_contract='b-p0-v03/v3')
    with pytest.raises(ValueError, match='MODEL_BATCH_SEMANTIC_CONTRACT_MISMATCH'):
        model.predict(Batch([{'input':examples[0]['input']}]))


def test_supplied_aligned_checkpoint_matches_A_and_C_protocol():
    from scripts.check_aligned_neural_checkpoint import check
    result = check()
    assert all(result['verification'].values())
    assert result['C_metrics']['counts']['n_failure'] == 0


def test_neural_inference_does_not_read_targets_or_private_ids():
    examples = load_records(ROOT / "data/p0/v0.3/p0_samples.json")
    view = copy.deepcopy(examples[0]["input"])
    clean = {"input": view}
    poisoned = {"input": copy.deepcopy(view), "target": {"states": "poisoned", "resume": "poisoned"},
                "id": "TEST_GOLD_IDENTIFIES_THE_ANSWER", "mechanism": "poisoned"}
    seed_everything(0)
    model = NeuralECJMF()
    assert model.predict(Batch([clean])) == model.predict(Batch([poisoned]))


def test_neural_future_leak_pair_remains_indistinguishable():
    examples = load_records(ROOT / "data/p0/p0_samples_v0.2.json")
    pair = [e for e in examples if e["family"] == "P07"]
    assert len(pair) == 2 and pair[0]["input"] == pair[1]["input"]
    seed_everything(0)
    native = NeuralECJMF().predict(Batch([{"input": e["input"]} for e in pair]))
    assert native[0] == native[1]


def test_conditional_step_is_not_reported_as_end_to_end_recovery_success():
    raw = json.loads((ROOT / "data/p0/p0_samples_v0.2.json").read_text(encoding="utf-8"))
    records, golds = prepare_dataset(raw)
    record, gold = next((r,g) for r,g in zip(records,golds) if g["resume_step"] is not None)
    obs = record["observation"]
    seed_everything(0)
    native = NeuralECJMF().predict(Batch([{"input": obs["structured_evidence"]}]), evidence=True)[0]
    native["t1"] = 0.4
    native["t2"] = {s:float(s == gold["resume_step"]) for s in obs["task_steps"]}
    public = normalize_neural_output(native, obs)
    assert max(native["t2"], key=native["t2"].get) == gold["resume_step"]
    assert public["resume_step"] is None
    scored = evaluate([{"sample_id":record["sample_id"],"status":"ok","prediction":public}], [gold], [record])
    assert scored["t2"]["top1_accuracy"] == 0
