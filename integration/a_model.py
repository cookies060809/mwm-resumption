"""C's executable fit/predict wrapper around A's actual structured model."""

import copy
import json
from collections import defaultdict

from integration.a_input_adapter import validate_structured_evidence
from integration.a_output_adapter import normalize_a_output
from models.ec_jmf.structured import ABLATIONS
from models.ecr_mwm.structured import infer
from models.ecr_mwm.training import TrainingExample, fit
from mwm_eval.schema import canonical_hash, file_hash


class StructuredECJMF:
    def __init__(self, seed=0, config=None, method_id="B10", variant="A0", train=True):
        self.method_id, self.seed = method_id, seed
        self.config = copy.deepcopy(config or {})
        self.variant, self.train = variant, train
        self.mechanisms = ABLATIONS[variant]
        self.transition_parameters = self.head_parameters = None
        self.training = {}

    def availability(self):
        return {"available": True, "reason": "A structured P0 model supplied in repository; CPU only"}

    def fit(self, train_pairs):
        examples, groups = [], defaultdict(list)
        for observation, gold in train_pairs:
            if gold["dataset_layer"] != "P0":
                raise ValueError("A reference wrapper currently accepts scripted P0 only")
            inputs = validate_structured_evidence(observation.get("structured_evidence"), observation)
            states = {factor: label for factor, label in gold["state_labels"].items()
                      if label not in {None, "UNKNOWN"} and gold["state_evidence"].get(factor)}
            targets = {"resume": (gold["resume_label"] == "resume" if gold["resume_label"] in {"resume", "not_resume"} else None),
                       "resume_mask": gold["resume_label"] in {"resume", "not_resume"},
                       "step": gold["resume_step"], "step_mask": gold["resume_step"] is not None,
                       "states": states}
            examples.append(TrainingExample(inputs, targets, "P0", "train", gold.get("pair_id", "")))
            if gold.get("pair_mechanism") == "future_leak":
                groups[gold["pair_id"]].append(len(examples)-1)
        if not examples:
            raise ValueError("A training/evidence declaration requires nonempty train split")
        pairs = []
        for members in groups.values():
            if len(members) == 2 and canonical_hash(examples[members[0]].inputs) == canonical_hash(examples[members[1]].inputs):
                pairs.append(tuple(members))  # identical evidence and identical model priors
        self.training = {"train_n": len(examples), "layer": "P0", "seed": self.seed,
            "variant": self.variant, "trained": self.train, "stages": [],
            "train_inputs_sha256": canonical_hash([example.inputs for example in examples]),
            "train_targets_sha256": canonical_hash([example.targets for example in examples]),
            "certified_identical_input_pairs": len(pairs),
            "pair_scope": "identical input views and same reference priors; no inferred hidden-world pairs"}
        if self.train:
            for stage in ("state", "joint"):
                epochs = self.config.get(stage + "_epochs", 1)
                if type(epochs) is not int or epochs < 0:
                    raise ValueError("stage epochs must be a nonnegative integer")
                if not epochs:
                    continue
                result = fit(examples, epochs=epochs, seed=self.seed, stage=stage,
                    mechanisms=self.mechanisms, transition_parameters=self.transition_parameters,
                    head_parameters=self.head_parameters, invariant_pairs=pairs,
                    learning_rate=self.config.get("learning_rate", 0.05))
                self.transition_parameters = result["transition_parameters"]
                self.head_parameters = result["head_parameters"]
                self.training["stages"].append(result)
        self.training["parameters_sha256"] = canonical_hash(
            {"transition": self.transition_parameters, "head": self.head_parameters})
        return self

    def predict(self, observation):
        if not self.training:
            raise ValueError("call fit to declare/freeze the train split first")
        # Engine validated this shared view before fit/evaluation. No source rows,
        # IDs, labels, snapshots or future paths are accessible here.
        view = copy.deepcopy(observation["structured_evidence"])
        payload = infer(view, transition_parameters=self.transition_parameters,
            head_parameters=self.head_parameters, mechanisms=self.mechanisms,
            method=self.config.get("inference", "exact"), seed=self.seed,
            particles=self.config.get("particles", 128),
            max_states=self.config.get("max_states", 10000))["prediction"]
        prediction = normalize_a_output(payload, observation, self.config.get("decision_threshold", 0.5))
        prediction["metadata"].update({"model_version": "a-structured/v0.2.0", "variant": self.variant,
            "trained": self.train, "parameters_sha256": self.training["parameters_sha256"],
            "usage": {"total_tokens": payload["cost"]["tokens"]},
            "graph_gate_applied": payload["t1_resume_probability"] == 0})
        return prediction

    def save_artifacts(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"seed_{self.seed}.json"
        checkpoint = {"format": "c-a-structured-checkpoint/1.0.0", "spec": self.spec(),
            "transition_parameters": self.transition_parameters, "head_parameters": self.head_parameters,
            "training": self.training}
        path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        return [{"path": f"checkpoints/{self.method_id}/{path.name}", "sha256": file_hash(path)}]

    def spec(self):
        return {"method_id": self.method_id, "implementation": "A StructuredModel + exact reference trainer",
            "model_version": "a-structured/v0.2.0", "strict_reproduction": False,
            "inference": self.config.get("inference", "exact"), "variant": self.variant,
            "trainable": self.train, "seed_control": "local_seed", "config": self.config,
            "training": {key: value for key, value in self.training.items() if key != "stages"},
            "limitations": "Finite exact reference; no neural text encoder, P1, LLM, MENTIS or calibrated probabilities. A factor uses latest salient event, not B key-event gold. A2 is coupling removal, not independent BCQ."}


def make_a_models(config, seed):
    settings = config.get("a_model", {})
    if not settings.get("enabled", False):
        return {}
    models = {"B10": StructuredECJMF(seed, settings),
              "B10_REFERENCE": StructuredECJMF(seed, settings, "B10_REFERENCE", train=False)}
    for variant in ("A1", "A2", "A3", "A4", "A5", "A6"):
        models[variant] = StructuredECJMF(seed, settings, variant, variant=variant)
    return models
