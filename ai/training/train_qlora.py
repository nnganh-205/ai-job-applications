"""Opt-in Colab/CUDA QLoRA pilot. Default validates data only; no downloads/training."""

import argparse
import json
from pathlib import Path

from ai.training.prepare_data import load_rows, validate_example


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--model', required=True, help='Exact Hugging Face model ID or local directory, not an Ollama tag')
    parser.add_argument('--output', required=True, help='New adapter directory')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--allow-download', action='store_true')
    parser.add_argument('--max-steps', type=int, default=20)
    parser.add_argument('--max-length', type=int, default=4096)
    args = parser.parse_args()
    rows = load_rows(args.data)
    for row in rows:
        if row.get('contract') != 'cv-plan-v1': raise SystemExit('Dataset contract is not cv-plan-v1')
        verified = validate_example(row)
        if row.get('split') != verified['split']: raise SystemExit('Split/group mismatch; prepare the data again')
    train = [row for row in rows if row['split'] == 'train']
    if not train or args.max_steps < 1 or args.max_length < 256: raise SystemExit('Missing training records or invalid limits')
    if Path(args.output).exists(): raise SystemExit('Output already exists; refusing overwrite')
    if not args.execute:
        print(json.dumps({'status': 'data_validated_only', 'train_records': len(train), 'training_started': False, 'model_downloaded': False}))
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments, default_data_collator
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    if not torch.cuda.is_available(): raise SystemExit('QLoRA requires a supported CUDA GPU; use Colab, not this Mac runtime')
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=not args.allow_download)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    examples = []
    for row in train:
        prompt = tokenizer.apply_chat_template(row['messages'][:-1], tokenize=True, add_generation_prompt=True, enable_thinking=False)
        answer = tokenizer(row['messages'][-1]['content'] + tokenizer.eos_token, add_special_tokens=False)['input_ids']
        ids = prompt + answer
        if len(ids) > args.max_length: continue  # Never truncate a JSON answer silently.
        pad = args.max_length - len(ids)
        examples.append({'input_ids': ids + [tokenizer.pad_token_id] * pad, 'attention_mask': [1] * len(ids) + [0] * pad,
                         'labels': [-100] * len(prompt) + answer + [-100] * pad})
    if not examples: raise SystemExit('All examples exceed max length; no training started')
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=not args.allow_download, device_map={'': 0},
                quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype))
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules='all-linear', task_type='CAUSAL_LM'))
    model.config.use_cache = False
    training = TrainingArguments(output_dir=args.output, max_steps=args.max_steps, per_device_train_batch_size=1,
                gradient_accumulation_steps=4, learning_rate=0.0002, gradient_checkpointing=True,
                bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16, logging_steps=1, save_strategy='no', report_to='none', seed=42)
    Trainer(model=model, args=training, train_dataset=examples, data_collator=default_data_collator).train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    Path(args.output, 'pilot_manifest.json').write_text(json.dumps({'contract': 'cv-plan-v1', 'base_model': args.model, 'max_steps': args.max_steps,
                  'examples_used': len(examples), 'examples_too_long': len(train) - len(examples), 'export': 'Hugging Face PEFT adapter', 'evaluated': False}))
    print('Adapter exported. Not evaluated or integrated into Ollama yet.')


if __name__ == '__main__': main()
