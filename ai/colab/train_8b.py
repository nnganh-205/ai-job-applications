"""Qwen3-8B with Unsloth QLoRA. Importing this module never starts training."""
from dataclasses import asdict, dataclass
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import time
import zipfile

os.environ.update(USE_TF='0', USE_FLAX='0', TOKENIZERS_PARALLELISM='false')
MODEL = 'Qwen/Qwen3-8B'
REVISION = 'b968826d9c46dd6066d109eabc6255188de91218'
RUN = 'run-8b-unsloth'


@dataclass(frozen=True)
class TrainConfig:
    max_length: int = 2048
    epochs: float = 1.0
    learning_rate: float = 5e-5
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    target_modules: tuple = ('q_proj', 'k_proj', 'v_proj', 'o_proj')
    precision: str = 'float16'
    optimizer: str = 'paged_adamw_8bit'
    warmup_ratio: float = 0.03
    scheduler: str = 'cosine'
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    adam_beta1: float = 0.9
    adam_beta2: float = 0.999
    adam_epsilon: float = 1e-8
    logging_steps: int = 10
    save_steps: int = 25
    save_total_limit: int = 2
    eval_steps: int = 100
    seed: int = 42
    generation_max_new_tokens: int = 384

    def __post_init__(self):
        for name in ('max_length', 'batch_size', 'gradient_accumulation_steps',
                     'lora_rank', 'lora_alpha', 'logging_steps', 'save_steps',
                     'save_total_limit', 'eval_steps', 'generation_max_new_tokens'):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('epochs', 'learning_rate', 'max_grad_norm', 'adam_epsilon'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        for name in ('warmup_ratio', 'lora_dropout', 'adam_beta1', 'adam_beta2'):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value < 1:
                raise ValueError(f'{name} must be in [0, 1)')
        if self.precision not in {'float16', 'bfloat16'}:
            raise ValueError('precision must be float16 or bfloat16')
        if self.weight_decay < 0 or not math.isfinite(self.weight_decay):
            raise ValueError('weight_decay must be finite and non-negative')
        if not self.target_modules or len(set(self.target_modules)) != len(self.target_modules):
            raise ValueError('target_modules must be non-empty and unique')


def load(work, config):
    # Unsloth must patch Transformers before any direct torch/transformers/peft imports.
    from unsloth import FastLanguageModel
    import torch
    from transformers import set_seed

    if not torch.cuda.is_available():
        raise RuntimeError('Select Kernel → Colab → GPU; this notebook requires CUDA.')
    if torch.cuda.device_count() != 1:
        raise RuntimeError('This notebook is configured for one GPU.')
    if config.precision == 'bfloat16' and not torch.cuda.is_bf16_supported():
        raise RuntimeError('This GPU does not support BF16. Use float16 for T4.')
    set_seed(config.seed)
    dtype = getattr(torch, config.precision)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL, revision=REVISION, use_exact_model_name=True,
        max_seq_length=config.max_length, dtype=dtype, load_in_4bit=True,
        full_finetuning=False, trust_remote_code=False, device_map={'': 0},
        use_gradient_checkpointing='unsloth', random_state=config.seed,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=config.lora_rank, lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout, target_modules=list(config.target_modules),
        bias='none', use_gradient_checkpointing='unsloth',
        random_state=config.seed, use_rslora=False, loftq_config=None,
    )
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    tokenizer.padding_side = 'right'
    # Keep the adapter portable; do not save an ephemeral local cache path as its base.
    for adapter in model.peft_config.values():
        adapter.base_model_name_or_path = MODEL
        adapter.revision = REVISION
    model.config.use_cache = False
    model.print_trainable_parameters()
    return tokenizer, model, dtype


def datasets(work, tokenizer, config):
    from torch.utils.data import Dataset
    from ai.colab.checkpoint_8b import atomic_json, sha256

    class Rows(Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            return self.rows[index]

    folder = Path(work) / 'ai/data/processed/cv8b-v1'
    manifest = json.loads((folder / 'manifest.json').read_text())
    output, counts, families = {}, {}, {}
    for split in ('train', 'validation', 'test'):
        path = folder / (split + '.jsonl')
        if sha256(path) != manifest['checksums'][path.name]:
            raise ValueError('Dataset checksum mismatch: ' + str(path))
        raw = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        families[split] = {row['family'] for row in raw}
        encoded, over_length = [], 0
        for row in raw:
            if row.get('source') == 'onet-translated':
                raise ValueError('Unverified translations must not enter this training run.')
            messages = row['messages']
            if messages[-1]['role'] != 'assistant' or not messages[-1]['content'].strip():
                raise ValueError('Missing assistant target: ' + row['id'])
            prompt = tokenizer.apply_chat_template(
                messages[:-1], tokenize=True, add_generation_prompt=True, enable_thinking=False,
            )
            answer = tokenizer(
                messages[-1]['content'] + tokenizer.eos_token, add_special_tokens=False,
            )['input_ids']
            if len(prompt) + len(answer) > config.max_length:
                over_length += 1
                continue
            encoded.append(dict(
                input_ids=prompt + answer, attention_mask=[1] * (len(prompt) + len(answer)),
                labels=[-100] * len(prompt) + answer,
            ))
        output[split] = Rows(encoded)
        counts[split] = dict(eligible=len(encoded), over_length=over_length, original=len(raw))
        if not encoded:
            raise ValueError('Empty split: ' + split)
    if (families['train'] & (families['validation'] | families['test'])
            or families['validation'] & families['test']):
        raise ValueError('Source-family leakage between splits')
    atomic_json(Path(work) / 'tokenization-audit.json', counts)
    # Do not silently drop samples from a run described as training the entire dataset.
    if any(item['over_length'] for item in counts.values()):
        raise ValueError('Some samples exceed max_length; inspect tokenization-audit.json before training.')
    print('Tokenized samples:', {key: value['eligible'] for key, value in counts.items()})
    return output, manifest


def run_identity(work, config):
    from ai.colab.checkpoint_8b import sha256, atomic_json

    work = Path(work)
    manifest = json.loads((work / 'ai/data/processed/cv8b-v1/manifest.json').read_text())
    packages = ('unsloth', 'unsloth_zoo', 'torch', 'torchvision', 'xformers', 'torchao',
                'transformers', 'peft', 'accelerate', 'bitsandbytes', 'trl', 'datasets',
                'numpy', 'huggingface_hub', 'safetensors')
    import torch
    environment = dict(packages={name: version(name) for name in packages}, cuda=torch.version.cuda)
    atomic_json(work / 'environment.json', environment)
    identity = dict(
        backend='unsloth-qlora-v1', model=MODEL, revision=REVISION,
        config=json.loads(json.dumps(asdict(config))), data=manifest['checksums'],
        quantization='nf4-double-4bit', gradient_checkpointing='unsloth',
        loss='assistant-only', packing=False, environment=environment,
        code={name: sha256(work / 'ai/colab' / name)
              for name in ('train_8b.py', 'checkpoint_8b.py', 'requirements-8b.txt')},
    )
    path = work / RUN / 'run-identity.json'
    if path.exists() and json.loads(path.read_text()) != identity:
        raise RuntimeError('Run configuration changed. Use a new run folder, or restore the original configuration.')
    atomic_json(path, identity)
    return identity


def trainer(work, tokenizer, model, data, config, persistent, identity):
    # FastLanguageModel patches this Trainer; preserve our pre-tokenized labels exactly.
    from transformers import Trainer, TrainingArguments, DataCollatorForSeq2Seq, TrainerCallback
    from ai.colab.checkpoint_8b import backup_checkpoint, require_drive

    persistent = require_drive(persistent)
    run = Path(work) / RUN
    args = TrainingArguments(
        output_dir=str(run / 'checkpoints'), num_train_epochs=config.epochs,
        learning_rate=config.learning_rate, per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=1, gradient_accumulation_steps=config.gradient_accumulation_steps,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant': False},
        fp16=config.precision == 'float16', bf16=config.precision == 'bfloat16',
        optim=config.optimizer, warmup_ratio=config.warmup_ratio,
        lr_scheduler_type=config.scheduler, max_grad_norm=config.max_grad_norm,
        weight_decay=config.weight_decay, adam_beta1=config.adam_beta1,
        adam_beta2=config.adam_beta2, adam_epsilon=config.adam_epsilon,
        logging_steps=config.logging_steps, logging_nan_inf_filter=False,
        save_strategy='steps', save_steps=config.save_steps, save_total_limit=config.save_total_limit,
        save_only_model=False, eval_strategy='steps', eval_steps=config.eval_steps,
        prediction_loss_only=True, report_to=[], seed=config.seed, data_seed=config.seed,
        group_by_length=True, dataloader_num_workers=0, save_safetensors=True,
        remove_unused_columns=False, disable_tqdm=False,
    )

    class BackupMonitor(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step == 1:
                control.should_save = True
            return control

        def on_log(self, args, state, control, logs=None, **kwargs):
            logs = logs or {}
            if any(isinstance(value, (int, float)) and not math.isfinite(value)
                   for value in logs.values()):
                raise RuntimeError('Non-finite training metric')
            with (run / 'progress.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(step=state.global_step, time=time.time(), **logs)) + '\n')

        def on_save(self, args, state, control, **kwargs):
            saved = backup_checkpoint(
                work, Path(args.output_dir) / f'checkpoint-{state.global_step}', persistent, identity,
            )
            print(f'Checkpoint {state.global_step} backed up: {saved.name}', flush=True)

    return Trainer(
        model=model, args=args, train_dataset=data['train'], eval_dataset=data['validation'],
        data_collator=DataCollatorForSeq2Seq(
            tokenizer, padding=True, label_pad_token_id=-100, pad_to_multiple_of=8,
        ), processing_class=tokenizer, callbacks=[BackupMonitor()],
    )


def evaluation_rows(work):
    folder = Path(work) / 'ai/data/processed/cv8b-v1'
    heldout = [json.loads(line) for line in (folder / 'test.jsonl').read_text().splitlines()]
    english = [row for row in heldout if row['task'] in ('cv_writer', 'cv_polish')][:12]
    with zipfile.ZipFile(Path(work) / 'output/colab/kltn-cv-writer-v6-720.zip') as archive:
        vi_test = [json.loads(line) for line in archive.read('data/test.jsonl').decode().splitlines()]
        vi_train = [json.loads(line) for line in archive.read('data/train.jsonl').decode().splitlines()]
    train_families = {family for row in vi_train for family in row['source_families']}
    if train_families & {family for row in vi_test for family in row['source_families']}:
        raise ValueError('Vietnamese evaluation family leakage')
    vietnamese = [{**row, 'id': row['sample_id']} for track in ('writer', 'polish')
                  for row in [item for item in vi_test if item['track'] == track][:6]]
    rows = english + vietnamese
    if len(rows) != 24:
        raise ValueError('Expected 24 generation evaluation cases')
    return rows


def probe(work, tokenizer, model, rows, filename, config):
    from unsloth import FastLanguageModel
    import torch
    from ai.colab.checkpoint_8b import atomic_json

    results = []
    FastLanguageModel.for_inference(model)
    try:
        for row in rows:
            inputs = tokenizer.apply_chat_template(
                row['messages'][:-1], tokenize=True, add_generation_prompt=True,
                enable_thinking=False, return_tensors='pt',
            ).to('cuda')
            with torch.inference_mode():
                generated = model.generate(
                    input_ids=inputs, attention_mask=torch.ones_like(inputs),
                    max_new_tokens=config.generation_max_new_tokens, do_sample=False,
                    use_cache=True, pad_token_id=tokenizer.pad_token_id,
                )
            text = tokenizer.decode(generated[0, inputs.shape[-1]:], skip_special_tokens=True)
            try:
                json.loads(text)
                valid = True
            except ValueError:
                valid = False
            results.append(dict(id=row['id'], output=text, json_valid=valid,
                                reference=row['messages'][-1]['content']))
            atomic_json(Path(work) / filename, results)
    finally:
        FastLanguageModel.for_training(model, use_gradient_checkpointing='unsloth')
        model.config.use_cache = False
    return results


def export_results(work, persistent):
    from ai.colab.checkpoint_8b import atomic_json, publish_file

    work = Path(work)
    run = work / RUN
    for name in ('train-result.json', 'evaluation.json', 'adapter/adapter_model.safetensors'):
        if not (run / name).is_file():
            raise RuntimeError('Train/evaluation not finished: ' + name)
    baseline = json.loads((work / 'base-generation.json').read_text())
    after = json.loads((work / 'adapter-generation.json').read_text())
    if len(baseline) != 24 or [row['id'] for row in baseline] != [row['id'] for row in after]:
        raise ValueError('Before/after evaluation cases do not match')
    archive = work / 'KLTN_8B_Results.zip'
    files = {path.relative_to(work).as_posix(): path for path in (run / 'adapter').rglob('*') if path.is_file()}
    for root in (work / 'ai/data/processed/cv8b-v1', work / 'ai/colab'):
        files.update({path.relative_to(work).as_posix(): path for path in root.rglob('*')
                      if path.is_file() and path.suffix in {'.py', '.txt', '.json', '.jsonl'}})
    for name in ('base-generation.json', 'adapter-generation.json', 'generation-eval-inputs.json',
                 'environment.json', 'tokenization-audit.json', f'{RUN}/progress.jsonl',
                 f'{RUN}/run-identity.json', f'{RUN}/train-result.json', f'{RUN}/evaluation.json'):
        path = work / name
        if path.is_file():
            files[name] = path
    from ai.colab.checkpoint_8b import sha256
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for name, path in files.items():
            output.write(path, name)
        output.writestr('result-checksums.json', json.dumps({n: sha256(p) for n, p in files.items()}))
    destination = publish_file(archive, Path(persistent) / archive.name)
    atomic_json(run / 'export.json', {'file': str(destination), 'sha256': sha256(destination)})
    return destination
